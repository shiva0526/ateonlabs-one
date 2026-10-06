from typing import Optional, List, Sequence
from datetime import date, datetime
from sqlalchemy import select, and_, desc
from sqlalchemy.orm import Session
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.audit_log import AuditLog

class AttendanceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, attendance_id: str) -> Optional[Attendance]:
        return self.db.execute(
            select(Attendance).where(Attendance.id == attendance_id)
        ).scalar_one_or_none()

    def get_by_employee_and_date(self, employee_id: str, work_date: date) -> Optional[Attendance]:
        return self.db.execute(
            select(Attendance).where(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.date == work_date
                )
            )
        ).scalar_one_or_none()

    def get_active_session(self, employee_id: str) -> Optional[Attendance]:
        """Find an attendance record with check_in set and check_out is null."""
        return self.db.execute(
            select(Attendance).where(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.check_in.is_not(None),
                    Attendance.check_out.is_(None)
                )
            ).order_by(desc(Attendance.date))
        ).scalars().first()

    def create(self, attendance: Attendance) -> Attendance:
        self.db.add(attendance)
        self.db.commit()
        self.db.refresh(attendance)
        return attendance

    def update(self, attendance: Attendance) -> Attendance:
        self.db.commit()
        self.db.refresh(attendance)
        return attendance

    def get_history(
        self, employee_id: str, start_date: date, end_date: date
    ) -> Sequence[Attendance]:
        return self.db.execute(
            select(Attendance).where(
                and_(
                    Attendance.employee_id == employee_id,
                    Attendance.date >= start_date,
                    Attendance.date <= end_date
                )
            ).order_by(Attendance.date.asc())
        ).scalars().all()

    def get_scoped_attendance(
        self, from_date: date, to_date: date, employee_ids: Optional[List[str]] = None
    ) -> Sequence[Attendance]:
        stmt = select(Attendance).where(
            and_(
                Attendance.date >= from_date,
                Attendance.date <= to_date
            )
        )
        if employee_ids is not None:
            stmt = stmt.where(Attendance.employee_id.in_(employee_ids))
        return self.db.execute(stmt.order_by(Attendance.date.asc())).scalars().all()

    def upsert_override(
        self, employee_id: str, work_date: date, status: str,
        check_in: Optional[datetime], check_out: Optional[datetime]
    ) -> Attendance:
        record = self.get_by_employee_and_date(employee_id, work_date)
        if record:
            record.status = status
            record.check_in = check_in
            record.check_out = check_out
            self.db.commit()
            self.db.refresh(record)
            return record
        else:
            new_record = Attendance(
                employee_id=employee_id,
                date=work_date,
                status=status,
                check_in=check_in,
                check_out=check_out,
            )
            return self.create(new_record)

    def log_audit(
        self, actor_id: Optional[str], actor_name: str, action: str,
        entity: str, entity_id: Optional[str], details: Optional[str]
    ) -> AuditLog:
        audit = AuditLog(
            actor_id=actor_id,
            actor_name=actor_name,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
        )
        self.db.add(audit)
        self.db.commit()
        return audit
