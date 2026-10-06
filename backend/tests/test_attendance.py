import pytest
from datetime import date, datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import Base
from app.api.deps import get_db, get_current_user, get_current_employee
from app.models.user import User
from app.models.employee import Employee
from app.models.attendance import Attendance

# In-memory SQLite for fast, isolated, deterministic unit testing
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
def test_user(db_session):
    user = db_session.query(User).filter_by(email="test.employee@ateonlabs.com").first()
    if not user:
        user = User(
            id="usr_test_123",
            name="Test Employee",
            email="test.employee@ateonlabs.com",
            password_hash="fake_hash",
            role="employee",
            department="Engineering",
            designation="Software Engineer",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user

@pytest.fixture
def test_employee(db_session, test_user):
    employee = db_session.query(Employee).filter_by(email=test_user.email).first()
    if not employee:
        employee = Employee(
            id="emp_test_123",
            user_id=test_user.id,
            name=test_user.name,
            email=test_user.email,
            designation=test_user.designation,
            status="active",
        )
        db_session.add(employee)
        db_session.commit()
        db_session.refresh(employee)
    return employee

@pytest.fixture
def client(db_session, test_user, test_employee):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_current_user():
        return test_user

    def override_get_current_employee():
        return test_employee

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_employee] = override_get_current_employee

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_root_and_health(client):
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "running" in res_root.json()["message"]

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json() == {"status": "healthy"}


def test_initial_attendance_status(client, db_session, test_employee):
    # Ensure no active records
    db_session.query(Attendance).filter_by(employee_id=test_employee.id).delete()
    db_session.commit()

    res = client.get("/api/v1/attendance/status")
    assert res.status_code == 200
    data = res.json()
    assert data["clocked_in"] is False
    assert data["on_break"] is False
    assert data["elapsed_seconds"] == 0


def test_clock_in_success(client, db_session, test_employee):
    db_session.query(Attendance).filter_by(employee_id=test_employee.id).delete()
    db_session.commit()

    res = client.post("/api/v1/attendance/clock-in", json={"notes": "Starting morning shift"})
    assert res.status_code == 200
    data = res.json()
    assert data["employee_id"] == test_employee.id
    assert data["check_in"] is not None
    assert data["check_out"] is None
    assert data["status"] == "present"


def test_duplicate_clock_in_conflict(client):
    # Second clock-in should fail with 409 Conflict
    res = client.post("/api/v1/attendance/clock-in", json={})
    assert res.status_code == 409
    assert "already clocked in" in res.json()["detail"]


def test_status_after_clock_in(client):
    res = client.get("/api/v1/attendance/status")
    assert res.status_code == 200
    data = res.json()
    assert data["clocked_in"] is True
    assert data["on_break"] is False


def test_break_lifecycle(client):
    # 1. Start break
    res_start = client.post("/api/v1/attendance/break/start", json={"notes": "Coffee break"})
    assert res_start.status_code == 200
    assert res_start.json()["on_break_since"] is not None

    # 2. Check status shows on_break
    res_status = client.get("/api/v1/attendance/status")
    assert res_status.json()["on_break"] is True

    # 3. Duplicate break start should fail with 409
    res_dup = client.post("/api/v1/attendance/break/start", json={})
    assert res_dup.status_code == 409

    # 4. End break
    res_end = client.post("/api/v1/attendance/break/end", json={})
    assert res_end.status_code == 200
    assert res_end.json()["on_break_since"] is None

    # 5. End break again without active break should fail with 400
    res_bad_end = client.post("/api/v1/attendance/break/end", json={})
    assert res_bad_end.status_code == 400


def test_clock_out_success(client):
    res = client.post("/api/v1/attendance/clock-out", json={"notes": "Shift complete"})
    assert res.status_code == 200
    data = res.json()
    assert data["check_out"] is not None

    # Status should now be clocked out
    res_status = client.get("/api/v1/attendance/status")
    assert res_status.json()["clocked_in"] is False


def test_clock_out_without_active_session_fails(client):
    res = client.post("/api/v1/attendance/clock-out", json={})
    assert res.status_code == 400
    assert "without an active clock-in" in res.json()["detail"]


def test_attendance_history(client, test_employee):
    today = datetime.now(timezone.utc).date()
    start_date = (today - timedelta(days=7)).isoformat()
    end_date = today.isoformat()

    res = client.get(f"/api/v1/attendance/history?start_date={start_date}&end_date={end_date}")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    assert data["items"][0]["status"] == "present"


def test_backward_compatible_toggle(client, db_session, test_employee):
    db_session.query(Attendance).filter_by(employee_id=test_employee.id).delete()
    db_session.commit()

    # Toggle clock_in
    res1 = client.post("/api/v1/attendance/toggle", json={"action": "clock_in"})
    assert res1.status_code == 200
    assert res1.json()["check_in"] is not None

    # Toggle break_start
    res2 = client.post("/api/v1/attendance/toggle", json={"action": "break_start"})
    assert res2.status_code == 200
    assert res2.json()["on_break_since"] is not None

    # Toggle break_end
    res3 = client.post("/api/v1/attendance/toggle", json={"action": "break_end"})
    assert res3.status_code == 200
    assert res3.json()["on_break_since"] is None

    # Toggle clock_out
    res4 = client.post("/api/v1/attendance/toggle", json={"action": "clock_out"})
    assert res4.status_code == 200
    assert res4.json()["check_out"] is not None
