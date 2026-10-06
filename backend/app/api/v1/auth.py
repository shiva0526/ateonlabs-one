from typing import Optional
from fastapi import APIRouter, Depends, Response, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, extract_token_from_request
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse, LogoutResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

class InviteRequest(BaseModel):
    email: str
    name: str
    role: str
    phone: str = ""
    department: str = "General"

@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue session token",
)
def login(
    request: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    service = AuthService(db)
    result = service.login(request)
    
    if result.success and result.token:
        response.set_cookie(
            key="ateon_session",
            value=result.token,
            httponly=True,
            samesite="lax",
            max_age=24 * 60 * 60,
            path="/",
        )
    return result

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get currently authenticated user profile",
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
        department=current_user.department or "",
        designation=current_user.designation or "",
        avatar=current_user.avatar or "",
        two_factor_enabled=current_user.two_factor_enabled,
    )

@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Log out and invalidate current session",
)
def logout(
    response: Response,
    token: Optional[str] = Depends(extract_token_from_request),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    service = AuthService(db)
    service.logout(token)
    response.delete_cookie(key="ateon_session", path="/")
    return LogoutResponse(success=True, message="Successfully logged out")

@router.post(
    "/invite",
    status_code=status.HTTP_200_OK,
    summary="Invite a new user — creates account and emails temp password",
)
def invite_user(
    request: InviteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Only admins and senior roles can invite
    allowed = ["ceo", "admin", "cto", "chro", "coo", "cfo", "legal", "hr"]
    if current_user.role not in allowed:
        return {"error": "Insufficient permissions"}

    service = AuthService(db)
    return service.invite_user(
        email=request.email,
        name=request.name,
        role=request.role,
        phone=request.phone,
        department=request.department,
        actor=current_user,
    )

@router.get(
    "/users",
    status_code=status.HTTP_200_OK,
    summary="List all users",
)
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.name.asc()).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "department": u.department or "Engineering",
            "designation": u.designation or u.role.upper(),
            "phone": u.phone or "",
            "avatar": u.avatar or "",
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]

@router.get(
    "/employees",
    status_code=status.HTTP_200_OK,
    summary="List all employees",
)
def list_employees(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.models.employee import Employee
    employees = db.query(Employee).order_by(Employee.name.asc()).all()
    return [
        {
            "id": e.id,
            "user_id": e.user_id,
            "name": e.name,
            "email": e.email,
            "designation": e.designation,
            "status": e.status,
            "phone": e.phone or "",
            "location": e.location or "Bangalore HQ",
            "department": {"id": e.department_id or "dept-1", "name": e.department_id or "Engineering"},
            "salary": e.salary if current_user.role in ["ceo", "cto", "cfo", "chro", "admin"] else None,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in employees
    ]

