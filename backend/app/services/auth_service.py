from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
import uuid
import random
import bcrypt
from jose import jwt
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.email import send_otp_email
from app.models.user import User
from app.models.session import Session as DbSession
from app.models.employee import Employee
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse

ROLE_MODULES: Dict[str, List[str]] = {
    "ceo": ["dashboard", "command", "organization", "users", "crm", "marketing", "hrms", "projects", "finance", "payroll", "procurement", "approvals", "chat", "legal", "analytics", "reports", "service-desk", "calendar", "audit", "ai", "workspace", "settings"],
    "admin": ["dashboard", "command", "organization", "users", "crm", "marketing", "hrms", "projects", "finance", "payroll", "procurement", "approvals", "chat", "legal", "analytics", "reports", "service-desk", "calendar", "audit", "ai", "workspace", "settings"],
    "hr": ["dashboard", "users", "crm", "projects", "procurement", "hrms", "payroll", "approvals", "chat", "reports", "service-desk", "calendar", "workspace", "settings"],
    "cfo": ["dashboard", "command", "crm", "marketing", "finance", "payroll", "procurement", "approvals", "chat", "analytics", "reports", "calendar", "audit", "ai", "workspace", "settings"],
    "coo": ["dashboard", "command", "organization", "crm", "hrms", "projects", "procurement", "approvals", "chat", "analytics", "reports", "service-desk", "calendar", "ai", "workspace", "settings"],
    "cto": ["dashboard", "command", "organization", "users", "crm", "marketing", "hrms", "projects", "finance", "payroll", "procurement", "approvals", "chat", "legal", "analytics", "reports", "service-desk", "calendar", "audit", "ai", "workspace", "settings"],
    "chro": ["dashboard", "command", "organization", "users", "hrms", "payroll", "approvals", "chat", "analytics", "reports", "service-desk", "calendar", "ai", "workspace", "settings"],
    "legal": ["dashboard", "legal", "approvals", "chat", "audit", "service-desk", "calendar", "workspace", "settings"],
    "manager": ["dashboard", "command", "crm", "hrms", "projects", "approvals", "chat", "reports", "service-desk", "calendar", "workspace", "settings"],
    "employee": ["dashboard", "projects", "chat", "service-desk", "calendar", "workspace", "settings"],
}

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8")
            )
        except Exception:
            return False

    @staticmethod
    def hash_password(password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def create_access_token(
        user_id: str,
        email: str,
        role: str,
        modules: Optional[List[str]] = None,
        expires_delta: timedelta = timedelta(days=1)
    ) -> str:
        now = datetime.now(timezone.utc)
        expire = now + expires_delta
        role_modules = modules or ROLE_MODULES.get(role, ROLE_MODULES["employee"])
        
        payload = {
            "id": user_id,
            "email": email,
            "role": role,
            "modules": role_modules,
            "jti": uuid.uuid4().hex,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def login(self, request: LoginRequest) -> LoginResponse:
        email = request.email.strip().lower()


        user = self.db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        if not self.verify_password(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # 2FA check if enabled
        if user.two_factor_enabled:
            if not request.otp_code:
                # Generate fresh 6-digit verification code
                otp = f"{random.randint(100000, 999999)}"
                user.two_factor_secret = otp
                self.db.add(user)
                self.db.commit()

                # Dispatch OTP to user's email
                sent = send_otp_email(to_email=user.email, otp_code=otp, user_name=user.name)

                return LoginResponse(
                    success=False,
                    require_otp=True,
                    error=None,
                    email_sent=sent,
                )
            
            if not user.two_factor_secret or user.two_factor_secret != request.otp_code.strip():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid verification code"
                )
            
            # Clear one-time code after successful verification
            user.two_factor_secret = None
            self.db.add(user)
            self.db.commit()

        # Generate JWT
        modules = ROLE_MODULES.get(user.role, ROLE_MODULES["employee"])
        token = self.create_access_token(user.id, user.email, user.role, modules=modules)
        expires_at = datetime.now(timezone.utc) + timedelta(days=1)

        # Store session in DB
        db_session = DbSession(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        self.db.add(db_session)
        self.db.commit()

        # Ensure employee profile exists
        employee = self.db.execute(
            select(Employee).where(
                (Employee.user_id == user.id) | (Employee.email == user.email)
            )
        ).scalar_one_or_none()

        if not employee:
            employee = Employee(
                user_id=user.id,
                name=user.name,
                email=user.email,
                designation=user.designation or "Employee",
                status="active"
            )
            self.db.add(employee)
            self.db.commit()

        user_out = UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            department=user.department or "",
            designation=user.designation or "",
            avatar=user.avatar or "",
            two_factor_enabled=user.two_factor_enabled
        )

        return LoginResponse(
            success=True,
            token=token,
            user=user_out,
            require_otp=False
        )

    def logout(self, token: Optional[str]) -> bool:
        if token:
            session = self.db.execute(
                select(DbSession).where(DbSession.token == token)
            ).scalar_one_or_none()
            if session:
                self.db.delete(session)
                self.db.commit()
        return True

    def invite_user(
        self,
        email: str,
        name: str,
        role: str,
        phone: str = "",
        department: str = "General",
        actor: Optional[User] = None,
    ) -> dict:
        """Create a new user with a temp password and email it to them."""
        import secrets
        from app.core.email import send_invite_email

        # Validate email format
        if not email or "@" not in email:
            return {"error": "Enter a valid email address"}

        # Check for duplicate
        existing = self.db.execute(
            select(User).where(User.email == email.strip().lower())
        ).scalar_one_or_none()
        if existing:
            return {"error": "Email already exists"}

        # Generate secure temp password
        temp_password = secrets.token_urlsafe(12)
        password_hash = self.hash_password(temp_password)

        user = User(
            name=name,
            email=email.strip().lower(),
            role=role,
            phone=phone or None,
            password_hash=password_hash,
            department=department,
            designation=role.upper(),
            avatar="",
            two_factor_enabled=False,
        )

        try:
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)

            # Ensure employee profile exists for HRMS and Command Centre
            from app.models.employee import Employee
            existing_emp = self.db.execute(
                select(Employee).where(Employee.email == user.email)
            ).scalar_one_or_none()
            if not existing_emp:
                emp = Employee(
                    user_id=user.id,
                    name=user.name,
                    email=user.email,
                    designation=role.upper(),
                    status="active",
                    phone=phone or None,
                )
                self.db.add(emp)
                self.db.commit()
        except Exception as e:
            self.db.rollback()
            return {"error": f"Failed to create user: {str(e)}"}

        # Send invite email
        sent = send_invite_email(
            to_email=user.email,
            name=name,
            role=role,
            temp_password=temp_password,
        )

        if not sent:
            # Rollback user if email fails
            self.db.delete(user)
            self.db.commit()
            return {"error": "Failed to send invitation email. Check SMTP configuration."}

        return {"success": True, "user_id": user.id}

