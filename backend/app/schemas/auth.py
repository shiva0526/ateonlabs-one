from typing import Optional
from pydantic import BaseModel, ConfigDict

class LoginRequest(BaseModel):
    email: str
    password: str
    otp_code: Optional[str] = None

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    role: str
    department: Optional[str] = ""
    designation: Optional[str] = ""
    avatar: Optional[str] = ""
    two_factor_enabled: Optional[bool] = False

class LoginResponse(BaseModel):
    success: bool = True
    token: Optional[str] = None
    user: Optional[UserResponse] = None
    require_otp: Optional[bool] = False
    error: Optional[str] = None
    email_sent: Optional[bool] = False

class LogoutResponse(BaseModel):
    success: bool = True
    message: str = "Logged out successfully"
