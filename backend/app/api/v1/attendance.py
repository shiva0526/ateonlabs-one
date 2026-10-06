from typing import Optional
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, get_current_employee, require_roles
from app.models.user import User
from app.models.employee import Employee
from app.services.attendance_service import AttendanceService
from app.schemas.attendance import (
    AttendanceStatusResponse,
    AttendanceRecordResponse,
    AttendanceHistoryResponse,
    ClockInRequest,
    ClockOutRequest,
    BreakStartRequest,
    BreakEndRequest,
    AttendanceToggleRequest,
    AttendanceOverrideRequest,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])

@router.get(
    "/status",
    response_model=AttendanceStatusResponse,
    summary="Get current employee live attendance status",
    description="Returns whether the employee is clocked in, currently on break, elapsed work duration, and active break duration.",
)
def get_attendance_status(
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AttendanceStatusResponse:
    service = AttendanceService(db)
    return service.get_status(employee)

@router.post(
    "/clock-in",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Clock in for work",
    description="Starts an active attendance session with authoritative server timestamp. Rejects if an active session already exists.",
)
def clock_in(
    request: Optional[ClockInRequest] = None,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AttendanceRecordResponse:
    service = AttendanceService(db)
    return service.clock_in(employee, request)

@router.post(
    "/clock-out",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Clock out of work",
    description="Clocks out of the current active session. Resolves any ongoing break and calculates total working duration.",
)
def clock_out(
    request: Optional[ClockOutRequest] = None,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AttendanceRecordResponse:
    service = AttendanceService(db)
    return service.clock_out(employee, request)

@router.post(
    "/break/start",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Start a break",
    description="Marks the start of a break within an active work session.",
)
def start_break(
    request: Optional[BreakStartRequest] = None,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AttendanceRecordResponse:
    service = AttendanceService(db)
    return service.start_break(employee, request)

@router.post(
    "/break/end",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="End a break",
    description="Ends the ongoing break and adds the elapsed break time to cumulative break duration.",
)
def end_break(
    request: Optional[BreakEndRequest] = None,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AttendanceRecordResponse:
    service = AttendanceService(db)
    return service.end_break(employee, request)

@router.post(
    "/toggle",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Toggle attendance action",
    description="Backward-compatible toggle endpoint supporting action: clock_in, clock_out, break_start, break_end.",
)
def toggle_attendance(
    payload: AttendanceToggleRequest,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AttendanceRecordResponse:
    service = AttendanceService(db)
    return service.toggle(employee, payload.action)

@router.get(
    "/history",
    response_model=AttendanceHistoryResponse,
    summary="Get attendance history",
    description="Returns daily attendance records for the authenticated employee within the specified date range.",
)
def get_attendance_history(
    start_date: Optional[date] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(default=None, description="End date (YYYY-MM-DD)"),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> AttendanceHistoryResponse:
    if not start_date:
        today = datetime.now(timezone.utc).date()
        start_date = date(today.year, today.month, 1)
    if not end_date:
        end_date = datetime.now(timezone.utc).date()

    service = AttendanceService(db)
    return service.get_history(employee, start_date, end_date)

@router.post(
    "/override",
    response_model=AttendanceRecordResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin attendance manual override",
    description="Allows authorized management roles to manually record or correct attendance entries.",
)
def override_attendance(
    payload: AttendanceOverrideRequest,
    current_user: User = Depends(require_roles(["ceo", "admin", "coo", "chro", "hr", "manager"])),
    db: Session = Depends(get_db),
) -> AttendanceRecordResponse:
    service = AttendanceService(db)
    return service.override_attendance(
        actor=current_user,
        employee_id=payload.employee_id,
        work_date=payload.date,
        status_val=payload.status,
        check_in=payload.check_in,
        check_out=payload.check_out,
    )

@router.get(
    "/today",
    summary="Get today's attendance records for all employees",
)
def get_today_attendance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.attendance import Attendance
    today = datetime.now(timezone.utc).date()
    records = db.query(Attendance).filter(Attendance.date == today).all()
    return [
        {
            "id": r.id,
            "employeeId": r.employee_id,
            "date": r.date.isoformat(),
            "status": r.status,
            "checkIn": r.check_in.isoformat() if r.check_in else None,
            "checkOut": r.check_out.isoformat() if r.check_out else None,
            "onBreakSince": r.on_break_since.isoformat() if r.on_break_since else None,
            "breakSeconds": r.break_seconds or 0,
            "location": getattr(r, "location", None),
            "lat": getattr(r, "lat", None),
            "lng": getattr(r, "lng", None),
        }
        for r in records
    ]

@router.get(
    "/employee/{employee_id}/history",
    summary="Get full past attendance history for an employee with filters",
)
def get_employee_attendance_history(
    employee_id: str,
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    month: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.attendance import Attendance
    from app.services.attendance_service import ensure_utc
    import calendar

    allowed_roles = ["ceo", "admin", "cto", "chro", "coo", "cfo", "hr", "manager"]
    target_emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not target_emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    if current_user.role not in allowed_roles and target_emp.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    query = db.query(Attendance).filter(Attendance.employee_id == employee_id)

    if start_date:
        query = query.filter(Attendance.date >= start_date)
    if end_date:
        query = query.filter(Attendance.date <= end_date)
    if month and len(month.split("-")) == 2:
        try:
            y, m = map(int, month.split("-"))
            last_day = calendar.monthrange(y, m)[1]
            query = query.filter(Attendance.date >= date(y, m, 1), Attendance.date <= date(y, m, last_day))
        except Exception:
            pass
    if status_filter and status_filter.lower() != "all":
        query = query.filter(Attendance.status == status_filter.lower())

    records = query.order_by(Attendance.date.desc()).all()

    service = AttendanceService(db)
    items = []
    for r in records:
        elapsed, breaks = service._calculate_durations(r)
        check_in_utc = ensure_utc(r.check_in)
        check_out_utc = ensure_utc(r.check_out)

        ci_str = check_in_utc.strftime("%I:%M %p") if check_in_utc else "-"
        co_str = check_out_utc.strftime("%I:%M %p") if check_out_utc else "-"

        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        hours_str = f"{h}h {m}m"

        items.append({
            "id": r.id,
            "employeeId": r.employee_id,
            "date": r.date.isoformat(),
            "status": r.status,
            "checkIn": check_in_utc.isoformat() if check_in_utc else None,
            "checkOut": check_out_utc.isoformat() if check_out_utc else None,
            "clockInFormatted": ci_str,
            "clockOutFormatted": co_str,
            "elapsedSeconds": elapsed,
            "breakSeconds": breaks,
            "hoursFormatted": hours_str,
            "notes": r.notes or "",
            "location": getattr(r, "location", None) or "Office HQ",
        })

    return {
        "employee": {
            "id": target_emp.id,
            "name": target_emp.name,
            "email": target_emp.email,
            "designation": target_emp.designation,
            "department": target_emp.department_id or "General",
        },
        "records": items,
        "totalCount": len(items),
    }
