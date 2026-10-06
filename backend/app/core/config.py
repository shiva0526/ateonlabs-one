from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BACKEND_DIR / ".env"

class Settings(BaseSettings):
    PROJECT_NAME: str = "ATEON One API"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ateonlabs"
    
    # Auth configuration (JWT secret shared with Next.js)
    SECRET_KEY: str = "dev-secret-key-ateon-one-2024-local"
    ALGORITHM: str = "HS256"
    
    # Realtime configuration (Node.js Socket.IO server bridge)
    NODE_BACKEND_URL: str = "http://localhost:3001"
    INTERNAL_SECRET: str = "dev_secret"
    
    # SMTP / Email configuration for OTP verification
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False

    # CORS Origins (allow Next.js frontend locally)
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.1.26:3000"
    ]

    model_config = SettingsConfigDict(
        env_file=(str(ENV_PATH), ".env"),
        env_ignore_empty=True,
        extra="ignore"
    )

settings = Settings()

