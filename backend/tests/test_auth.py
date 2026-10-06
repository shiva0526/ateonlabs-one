import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import bcrypt

from app.main import app
from app.db.session import Base
from app.api.deps import get_db
from app.models.user import User
from app.models.employee import Employee
from app.models.session import Session as DbSession
from app.services.auth_service import AuthService

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def seed_user(db_session):
    user = db_session.query(User).filter_by(email="auth.test@ateonlabs.com").first()
    if not user:
        pwd_hash = AuthService.hash_password("testpassword123")
        user = User(
            id="usr_auth_test_123",
            name="Auth Test User",
            email="auth.test@ateonlabs.com",
            password_hash=pwd_hash,
            role="admin",
            department="IT",
            designation="Admin",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user

def test_login_success(client, seed_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "auth.test@ateonlabs.com", "password": "testpassword123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["token"] is not None
    assert data["user"]["email"] == "auth.test@ateonlabs.com"
    assert "ateon_session" in response.cookies

def test_login_invalid_password(client, seed_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "auth.test@ateonlabs.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]

def test_login_nonexistent_user(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "doesnotexist@ateonlabs.com", "password": "somepassword"}
    )
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]

def test_get_me_with_token(client, seed_user):
    # First login to get token
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "auth.test@ateonlabs.com", "password": "testpassword123"}
    )
    token = login_res.json()["token"]

    # Call /me with Bearer token
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "auth.test@ateonlabs.com"
    assert data["role"] == "admin"

def test_logout(client, seed_user):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "auth.test@ateonlabs.com", "password": "testpassword123"}
    )
    token = login_res.json()["token"]

    response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

def test_two_factor_auth_flow(client, db_session, seed_user):
    # Enable 2FA on seed user
    seed_user.two_factor_enabled = True
    db_session.add(seed_user)
    db_session.commit()

    # Step 1: Login without OTP triggers 2FA
    res1 = client.post(
        "/api/v1/auth/login",
        json={"email": "auth.test@ateonlabs.com", "password": "testpassword123"}
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["require_otp"] is True
    assert data1["token"] is None

    # Retrieve generated OTP from DB
    db_session.refresh(seed_user)
    otp = seed_user.two_factor_secret
    assert otp is not None
    assert len(otp) == 6

    # Step 2: Login with wrong OTP fails
    res_wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "auth.test@ateonlabs.com", "password": "testpassword123", "otp_code": "000000"}
    )
    assert res_wrong.status_code == 401

    # Step 3: Login with correct OTP succeeds
    res_correct = client.post(
        "/api/v1/auth/login",
        json={"email": "auth.test@ateonlabs.com", "password": "testpassword123", "otp_code": otp}
    )
    assert res_correct.status_code == 200
    data_correct = res_correct.json()
    assert data_correct["success"] is True
    assert data_correct["token"] is not None

    # Step 4: OTP cleared in DB
    db_session.refresh(seed_user)
    assert seed_user.two_factor_secret is None
    seed_user.two_factor_enabled = False
    db_session.add(seed_user)
    db_session.commit()

def test_unregistered_email_rejected(client):
    res_gmail = client.post(
        "/api/v1/auth/login",
        json={"email": "shiva@outlook.com", "password": "password123"}
    )
    assert res_gmail.status_code == 401
    assert "Invalid credentials" in res_gmail.json()["detail"]


def test_invite_user_success_and_duplicate(client, db_session, seed_user, monkeypatch):
    # Ensure 2FA is off for this user so simple login gives a token
    seed_user.two_factor_enabled = False
    db_session.add(seed_user)
    db_session.commit()
    # Mock send_invite_email so it doesn't try actual network SMTP in tests
    from unittest.mock import MagicMock
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("app.core.email.send_invite_email", mock_send)

    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "auth.test@ateonlabs.com", "password": "testpassword123"}
    )
    token = login_res.json()["token"]

    # Invite a new team member
    res = client.post(
        "/api/v1/auth/invite",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "newmember@ateonlabs.com",
            "name": "New Member",
            "role": "engineer",
            "phone": "+91 9876543210"
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("success") is True
    assert "user_id" in data
    mock_send.assert_called_once()

    # Inviting the same email again should return duplicate error
    res_dup = client.post(
        "/api/v1/auth/invite",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "newmember@ateonlabs.com",
            "name": "New Member Duplicate",
            "role": "engineer"
        }
    )
    assert res_dup.status_code == 200
    assert "Email already exists" in res_dup.json().get("error", "")

