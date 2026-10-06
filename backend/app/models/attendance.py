from typing import Optional
from datetime import date, datetime
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from app.models.base import generate_id, TimestampMixin

class Attendance(Base, TimestampMixin):
    __tablename__ = "attendance"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=generate_id)
    employee_id: Mapped[str] = mapped_column(String(64), ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False)
    
    # Calendar date of attendance record
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # Status: 'present', 'absent', 'leave', 'wfh', 'holiday'
    status: Mapped[str] = mapped_column(String(50), default="present", nullable=False)
    
    # Authoritative server-side timestamps (UTC)
    check_in: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    on_break_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Cumulative break duration in seconds
    break_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Optional client notes / GPS location metadata for verification
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendances")

    # Enforce one daily record per employee
    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_attendance_employee_date"),
        Index("idx_attendance_employee_date", "employee_id", "date"),
    )
