import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

class RealtimeAdapter:
    @staticmethod
    async def emit_to_org(event: str, data: dict) -> None:
        """
        Emit a realtime event to the organization room via the Node.js internal webhook.
        Fails silently and non-blockingly if Node.js server is not reachable.
        """
        payload = {
            "secret": settings.INTERNAL_SECRET,
            "room": "org",
            "event": event,
            "data": data,
        }
        url = f"{settings.NODE_BACKEND_URL}/api/internal/emit"
        try:
            async with httpx.AsyncClient(timeout=0.2) as client:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    logger.warning(f"Realtime emit failed with status {response.status_code}")
        except Exception:
            pass

    @staticmethod
    def sync_emit_to_org(event: str, data: dict) -> None:
        """Synchronous version of emit_to_org for non-async contexts."""
        payload = {
            "secret": settings.INTERNAL_SECRET,
            "room": "org",
            "event": event,
            "data": data,
        }
        url = f"{settings.NODE_BACKEND_URL}/api/internal/emit"
        try:
            with httpx.Client(timeout=0.1) as client:
                client.post(url, json=payload)
        except Exception:
            pass
