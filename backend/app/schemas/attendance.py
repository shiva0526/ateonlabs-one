from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field

# ─── Request Schemas ───

class ClockInRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500, description="Optional note or GPS location string")
    lat: Optional[float] = Field(default=None, description="Optional GPS latitude")
    lng: Optional[float] = Field(default=None, description="Optional GPS longitude")

class ClockOutRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)

class BreakStartRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)

class BreakEndRequest(BaseModel):
    notes: Optional[str] = Field(default=None, max_length=500)

class AttendanceToggleRequest(BaseModel):
    action: str = Field(..., pattern="^(clock_in|clock_out|break_start|break_end)$")

class AttendanceOverrideRequest(BaseModel):
    employee_id: str
    date: date
    status: str = Field(default="present", pattern="^(present|absent|leave|wfh|holiday)$")
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None

# ─── Response Schemas ───

class AttendanceStatusResponse(BaseModel):
    clocked_in: bool
    on_break: bool
    check_in_time: Optional[datetime] = None
    elapsed_seconds: int = 0
    break_seconds: int = 0
    status: str = "present"
    formatted_duration: str = "00:00:00"

    model_config = ConfigDict(from_attributes=True)

class AttendanceRecordResponse(BaseModel):
    id: str
    employee_id: str
    date: date
    status: str
    check_in: Optional[datetime] = None
    check_out: Optional[datetime] = None
    on_break_since: Optional[datetime] = None
    break_seconds: int
    elapsed_seconds: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AttendanceHistoryItem(BaseModel):
    date: str
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    elapsed_seconds: int = 0
    break_seconds: int = 0
    status: str = "present"

class AttendanceHistoryResponse(BaseModel):
    items: List[AttendanceHistoryItem]
    total_count: int

class ActionSuccessResponse(BaseModel):
    success: bool = True
    message: str = "Action completed successfully"
