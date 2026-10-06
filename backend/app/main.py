from typing import Optional, Any
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.config import settings
from app.api.v1 import api_v1_router
from app.realtime.socket_server import get_socket_app, sio

fastapi_app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API v1 routers
fastapi_app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@fastapi_app.get("/health")
def health_check():
    return {"status": "healthy"}


@fastapi_app.get("/")
def root():
    return {"message": f"{settings.PROJECT_NAME} is running"}


class InternalEmitRequest(BaseModel):
    secret: str
    room: Optional[str] = None
    event: str
    data: Optional[Any] = None


# Top-level internal emit endpoint (replaces node server.js /api/internal/emit)
@fastapi_app.post("/api/internal/emit")
async def root_internal_emit(payload: InternalEmitRequest):
    if payload.secret != settings.INTERNAL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid internal secret",
        )
    if payload.room:
        await sio.emit(payload.event, payload.data, room=payload.room)
    else:
        await sio.emit(payload.event, payload.data)
    return {"status": "ok"}


# ASGI application mounted with real-time Socket.IO and WebRTC support
app = get_socket_app(fastapi_app)
