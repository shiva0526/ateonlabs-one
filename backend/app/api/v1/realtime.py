from typing import Optional, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.realtime.socket_server import sio

router = APIRouter(tags=["realtime"])

class InternalEmitRequest(BaseModel):
    secret: str
    room: Optional[str] = None
    event: str
    data: Optional[Any] = None

@router.post("/internal/emit", summary="Internal emit bridge for server actions")
async def internal_emit_v1(payload: InternalEmitRequest):
    if payload.secret != settings.INTERNAL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid internal secret"
        )
    
    if payload.room:
        await sio.emit(payload.event, payload.data, room=payload.room)
    else:
        await sio.emit(payload.event, payload.data)
        
    return {"status": "ok"}
