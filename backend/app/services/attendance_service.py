from typing import Optional, List, Tuple
from datetime import datetime, date, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.user import User
from app.repositories.attendance_repository import AttendanceRepository
from app.adapters.realtime_adapter import RealtimeAdapter
from app.schemas.attendance import (
    AttendanceStatusResponse,
    AttendanceRecordResponse,
    AttendanceHistoryItem,
    AttendanceHistoryResponse,
    ClockInRequest,
    ClockOutRequest,
    BreakStartRequest,
    BreakEndRequest,
)

def format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure a datetime object is timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

class AttendanceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AttendanceRepository(db)

    def _get_current_time(self) -> datetime:
        """Server-authoritative UTC timestamp."""
        return datetime.now(timezone.utc)

    def _get_today_date(self) -> date:
        """Server-authoritative UTC date."""
        return datetime.now(timezone.utc).date()

    def _calculate_durations(self, record: Optional[Attendance]) -> Tuple[int, int]:
        """
        Calculate (elapsed_working_seconds, break_seconds).
        elapsed_working_seconds = (now/checkout - check_in) - total_break_seconds
        """
        if not record or not record.check_in:
            return 0, 0

        now = self._get_current_time()
        check_in = ensure_utc(record.check_in)
        check_out = ensure_utc(record.check_out)
        on_break_since = ensure_utc(record.on_break_since)

        end_time = check_out or now

        gross_seconds = max(0, int((end_time - check_in).total_seconds()))
        break_seconds = record.break_seconds or 0

        # Add currently active ongoing break if not checked out
        if on_break_since and not check_out:
            active_break = max(0, int((now - on_break_since).total_seconds()))
            break_seconds += active_break

        net_working_seconds = max(0, gross_seconds - break_seconds)
        return net_working_seconds, break_seconds

    def get_status(self, employee: Employee) -> AttendanceStatusResponse:
        """Return the employee's current live attendance state."""
        today = self._get_today_date()
        record = self.repo.get_by_employee_and_date(employee.id, today)

        if not record:
            # Check for any active session from previous day (e.g. night shift)
            record = self.repo.get_active_session(employee.id)

        if not record or not record.check_in or record.check_out:
            return AttendanceStatusResponse(
                clocked_in=False,
                on_break=False,
                check_in_time=ensure_utc(record.check_in) if record else None,
                elapsed_seconds=0,
                break_seconds=record.break_seconds if record else 0,
                status=record.status if record else "present",
                formatted_duration="00:00:00",
            )

        elapsed_seconds, break_seconds = self._calculate_durations(record)
        is_on_break = record.on_break_since is not None

        return AttendanceStatusResponse(
            clocked_in=True,
            on_break=is_on_break,
            check_in_time=ensure_utc(record.check_in),
            elapsed_seconds=elapsed_seconds,
            break_seconds=break_seconds,
            status=record.status,
            formatted_duration=format_duration(elapsed_seconds),
        )

    def clock_in(self, employee: Employee, request: Optional[ClockInRequest] = None) -> AttendanceRecordResponse:
        """Start a work session with server-authoritative timestamp."""
        active_session = self.repo.get_active_session(employee.id)
        if active_session:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Employee is already clocked in with an active attendance session.",
            )

        now = self._get_current_time()
        today = now.date()

        existing_today = self.repo.get_by_employee_and_date(employee.id, today)
        if existing_today and existing_today.check_out:
            # Re-opening / continuing session for today
            existing_today.check_out = None
            existing_today.check_in = existing_today.check_in or now
            if request and request.notes:
                existing_today.notes = request.notes
            record = self.repo.update(existing_today)
        else:
            record = Attendance(
                employee_id=employee.id,
                date=today,
                status="present",
                check_in=now,
                check_out=None,
                on_break_since=None,
                break_seconds=0,
                notes=request.notes if request else None,
            )
            record = self.repo.create(record)

        # Broadcast realtime event
        RealtimeAdapter.sync_emit_to_org("attendance:update", {
            "employeeId": employee.id,
            "name": employee.name,
            "action": "clock_in",
        })

        elapsed, breaks = self._calculate_durations(record)
        return AttendanceRecordResponse(
            id=record.id,
            employee_id=record.employee_id,
            date=record.date,
            status=record.status,
            check_in=ensure_utc(record.check_in),
            check_out=ensure_utc(record.check_out),
            on_break_since=ensure_utc(record.on_break_since),
            break_seconds=breaks,
            elapsed_seconds=elapsed,
            created_at=ensure_utc(record.created_at) or now,
            updated_at=ensure_utc(record.updated_at) or now,
        )

    def clock_out(self, employee: Employee, request: Optional[ClockOutRequest] = None) -> AttendanceRecordResponse:
        """End the active work session and calculate authoritative durations."""
        active_session = self.repo.get_active_session(employee.id)
        if not active_session:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot clock out without an active clock-in session.",
            )

        now = self._get_current_time()

        # If employee is currently on break, resolve break before checkout
        if active_session.on_break_since:
            on_break_since = ensure_utc(active_session.on_break_since)
            break_duration = max(0, int((now - on_break_since).total_seconds()))
            active_session.break_seconds = (active_session.break_seconds or 0) + break_duration
            active_session.on_break_since = None

        active_session.check_out = now
        if request and request.notes:
            active_session.notes = (active_session.notes or "") + f" [Out: {request.notes}]"

        record = self.repo.update(active_session)

        # Broadcast realtime event
        RealtimeAdapter.sync_emit_to_org("attendance:update", {
            "employeeId": employee.id,
            "name": employee.name,
            "action": "clock_out",
        })

        elapsed, breaks = self._calculate_durations(record)
        return AttendanceRecordResponse(
            id=record.id,
            employee_id=record.employee_id,
            date=record.date,
            status=record.status,
            check_in=ensure_utc(record.check_in),
            check_out=ensure_utc(record.check_out),
            on_break_since=ensure_utc(record.on_break_since),
            break_seconds=breaks,
            elapsed_seconds=elapsed,
            created_at=ensure_utc(record.created_at) or now,
            updated_at=ensure_utc(record.updated_at) or now,
        )

    def start_break(self, employee: Employee, request: Optional[BreakStartRequest] = None) -> AttendanceRecordResponse:
        """Start a break session."""
        active_session = self.repo.get_active_session(employee.id)
        if not active_session:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot start a break without an active clock-in session.",
            )

        if active_session.on_break_since is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Employee is already on an active break.",
            )

        now = self._get_current_time()
        active_session.on_break_since = now
        record = self.repo.update(active_session)

        RealtimeAdapter.sync_emit_to_org("attendance:update", {
            "employeeId": employee.id,
            "name": employee.name,
            "action": "break_start",
        })

        elapsed, breaks = self._calculate_durations(record)
        return AttendanceRecordResponse(
            id=record.id,
            employee_id=record.employee_id,
            date=record.date,
            status=record.status,
            check_in=ensure_utc(record.check_in),
            check_out=ensure_utc(record.check_out),
            on_break_since=ensure_utc(record.on_break_since),
            break_seconds=breaks,
            elapsed_seconds=elapsed,
            created_at=ensure_utc(record.created_at) or now,
            updated_at=ensure_utc(record.updated_at) or now,
        )

    def end_break(self, employee: Employee, request: Optional[BreakEndRequest] = None) -> AttendanceRecordResponse:
        """End an active break session and accumulate break duration."""
        active_session = self.repo.get_active_session(employee.id)
        if not active_session or active_session.on_break_since is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot end break: Employee is not currently on break.",
            )

        now = self._get_current_time()
        on_break_since = ensure_utc(active_session.on_break_since)
        break_duration = max(0, int((now - on_break_since).total_seconds()))
        active_session.break_seconds = (active_session.break_seconds or 0) + break_duration
        active_session.on_break_since = None

        record = self.repo.update(active_session)

        RealtimeAdapter.sync_emit_to_org("attendance:update", {
            "employeeId": employee.id,
            "name": employee.name,
            "action": "break_end",
        })

        elapsed, breaks = self._calculate_durations(record)
        return AttendanceRecordResponse(
            id=record.id,
            employee_id=record.employee_id,
            date=record.date,
            status=record.status,
            check_in=ensure_utc(record.check_in),
            check_out=ensure_utc(record.check_out),
            on_break_since=ensure_utc(record.on_break_since),
            break_seconds=breaks,
            elapsed_seconds=elapsed,
            created_at=ensure_utc(record.created_at) or now,
            updated_at=ensure_utc(record.updated_at) or now,
        )

    def toggle(self, employee: Employee, action: str) -> AttendanceRecordResponse:
        """Backward-compatible toggle handler."""
        if action == "clock_in":
            return self.clock_in(employee)
        elif action == "clock_out":
            return self.clock_out(employee)
        elif action == "break_start":
            return self.start_break(employee)
        elif action == "break_end":
            return self.end_break(employee)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action: '{action}'. Must be one of clock_in, clock_out, break_start, break_end.",
            )

    def get_history(self, employee: Employee, start_date: date, end_date: date) -> AttendanceHistoryResponse:
        """Retrieve historical attendance records for an employee."""
        records = self.repo.get_history(employee.id, start_date, end_date)
        items: List[AttendanceHistoryItem] = []

        for r in records:
            elapsed, breaks = self._calculate_durations(r)
            check_in_utc = ensure_utc(r.check_in)
            check_out_utc = ensure_utc(r.check_out)

            items.append(AttendanceHistoryItem(
                date=f"{r.date.isoformat()}T00:00:00.000Z",
                check_in=check_in_utc.isoformat() if check_in_utc else None,
                check_out=check_out_utc.isoformat() if check_out_utc else None,
                elapsed_seconds=elapsed,
                break_seconds=breaks,
                status=r.status,
            ))

        return AttendanceHistoryResponse(items=items, total_count=len(items))

    def override_attendance(
        self, actor: User, employee_id: str, work_date: date, status_val: str,
        check_in: Optional[datetime], check_out: Optional[datetime]
    ) -> AttendanceRecordResponse:
        """Admin override to record or fix an employee attendance record."""
        now = self._get_current_time()
        record = self.repo.upsert_override(
            employee_id=employee_id,
            work_date=work_date,
            status=status_val,
            check_in=check_in,
            check_out=check_out,
        )

        # Log audit
        self.repo.log_audit(
            actor_id=actor.id,
            actor_name=actor.name,
            action="hrms.attendance.override",
            entity="Attendance",
            entity_id=record.id,
            details=f"Date: {work_date}, Status: {status_val}, In: {check_in}, Out: {check_out}",
        )

        elapsed, breaks = self._calculate_durations(record)
        return AttendanceRecordResponse(
            id=record.id,
            employee_id=record.employee_id,
            date=record.date,
            status=record.status,
            check_in=ensure_utc(record.check_in),
            check_out=ensure_utc(record.check_out),
            on_break_since=ensure_utc(record.on_break_since),
            break_seconds=breaks,
            elapsed_seconds=elapsed,
            created_at=ensure_utc(record.created_at) or now,
            updated_at=ensure_utc(record.updated_at) or now,
        )
