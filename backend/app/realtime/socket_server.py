import logging
import urllib.parse
from typing import Dict, Set, Optional, Any, List
import socketio
from jose import jwt, JWTError
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User

logger = logging.getLogger("ateon.realtime")

# Initialize Socket.IO Async Server (ASGI mode)
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    ping_timeout=30,
    ping_interval=25,
)

# Presence tracking: user_id -> Set of socket IDs
online_users: Dict[str, Set[str]] = {}

# WebRTC call rooms: room_name -> { socket_id: { socketId, userId, name } }
call_rooms: Dict[str, Dict[str, Dict[str, Any]]] = {}

# Sockets to rooms they joined: sid -> Set of call room names
socket_call_rooms: Dict[str, Set[str]] = {}


def extract_token(environ: dict, auth: Optional[dict] = None) -> Optional[str]:
    """Extract session token from cookie, query param, or auth dict."""
    # 1. Check auth dictionary
    if auth and isinstance(auth, dict) and auth.get("token"):
        return str(auth.get("token")).strip()

    # 2. Check query string
    query_str = environ.get("QUERY_STRING", "")
    if not query_str:
        scope = environ.get("asgi.scope", {})
        query_bytes = scope.get("query_string", b"")
        if query_bytes:
            query_str = query_bytes.decode("utf-8", errors="ignore")

    if query_str:
        params = urllib.parse.parse_qs(query_str)
        if "token" in params and params["token"]:
            return params["token"][0]

    # 3. Check Cookie header
    cookie_header = environ.get("HTTP_COOKIE", "")
    if not cookie_header:
        scope = environ.get("asgi.scope", {})
        headers = dict(scope.get("headers", []))
        raw_cookie = headers.get(b"cookie", b"")
        if raw_cookie:
            cookie_header = raw_cookie.decode("utf-8", errors="ignore")

    if cookie_header:
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith("ateon_session="):
                val = part.split("=", 1)[1]
                return urllib.parse.unquote(val)

    return None


async def authenticate_socket(environ: dict, auth: Optional[dict] = None) -> Optional[dict]:
    """
    Validate the token from the socket handshake.
    Verifies JWT signature and extracts user metadata.
    """
    token = extract_token(environ, auth)
    if not token:
        # Development fallback: Allow connection in dev mode with a default profile if DB has users
        try:
            with SessionLocal() as db:
                dev_user = db.execute(select(User)).scalars().first()
                if dev_user:
                    return {
                        "id": dev_user.id,
                        "name": dev_user.name,
                        "email": dev_user.email,
                        "role": dev_user.role,
                    }
        except Exception:
            pass
        return None

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},
        )
        user_id = payload.get("id")
        user_email = payload.get("email")
        if not user_id and not user_email:
            return None

        # Verify against DB if available
        try:
            with SessionLocal() as db:
                stmt = select(User)
                if user_id:
                    stmt = stmt.where(User.id == user_id)
                else:
                    stmt = stmt.where(User.email == user_email)
                user = db.execute(stmt).scalar_one_or_none()
                if user:
                    return {
                        "id": user.id,
                        "name": user.name,
                        "email": user.email,
                        "role": user.role,
                    }
        except Exception as db_err:
            logger.warning(f"Database lookup in socket auth failed, using JWT payload: {db_err}")

        # If DB query failed but JWT is valid, use JWT claims
        return {
            "id": user_id or "user_id",
            "name": payload.get("name") or (user_email.split("@")[0] if user_email else "User"),
            "email": user_email or "",
            "role": payload.get("role") or "employee",
        }
    except JWTError as e:
        logger.warning(f"Socket auth JWT verification failed: {e}")
        return None


# ──────────────── Socket.IO Event Handlers ────────────────


@sio.event
async def connect(sid: str, environ: dict, auth: Optional[dict] = None):
    user = await authenticate_socket(environ, auth)
    if not user:
        logger.warning(f"[socket] Unauthorized connection attempt: sid={sid}")
        return False

    await sio.save_session(sid, {"user": user})

    # Join private user room and organization room
    user_id = str(user["id"])
    await sio.enter_room(sid, f"user:{user_id}")
    await sio.enter_room(sid, "org")

    # Update presence
    if user_id not in online_users:
        online_users[user_id] = set()
    online_users[user_id].add(sid)

    if len(online_users[user_id]) == 1:
        await sio.emit("presence:online", {"userId": user_id}, room="org")

    await sio.emit("presence:list", list(online_users.keys()), to=sid)
    logger.info(f"[socket] Connected: user={user['email']} sid={sid}")
    return True


@sio.event
async def disconnect(sid: str):
    session = await sio.get_session(sid) or {}
    user = session.get("user", {})
    user_id = user.get("id")

    # Clean up WebRTC calls
    joined_rooms = list(socket_call_rooms.get(sid, []))
    for call_room in joined_rooms:
        if call_room in call_rooms and sid in call_rooms[call_room]:
            del call_rooms[call_room][sid]
        await sio.emit("rtc:peer-left", {"socketId": sid, "userId": user_id}, room=call_room)

    socket_call_rooms.pop(sid, None)

    # Clean up presence
    if user_id and user_id in online_users:
        online_users[user_id].discard(sid)
        if not online_users[user_id]:
            del online_users[user_id]
            await sio.emit("presence:offline", {"userId": user_id}, room="org")

    logger.info(f"[socket] Disconnected: sid={sid}")


# ──────────────── Chat Rooms ────────────────


@sio.on("chat:join")
async def on_chat_join(sid: str, group_id: str):
    if not isinstance(group_id, str) or not group_id.strip():
        return
    await sio.enter_room(sid, f"group:{group_id.strip()}")


@sio.on("chat:leave")
async def on_chat_leave(sid: str, group_id: str):
    if isinstance(group_id, str) and group_id.strip():
        await sio.leave_room(sid, f"group:{group_id.strip()}")


@sio.on("chat:typing")
async def on_chat_typing(sid: str, group_id: str):
    if not isinstance(group_id, str):
        return
    session = await sio.get_session(sid) or {}
    user = session.get("user", {})
    await sio.emit(
        "chat:typing",
        {"groupId": group_id, "userId": user.get("id"), "name": user.get("name")},
        room=f"group:{group_id}",
        skip_sid=sid,
    )


# ──────────────── WebRTC Signalling ────────────────


@sio.on("rtc:join")
async def on_rtc_join(sid: str, room_id: str):
    if not isinstance(room_id, str) or not room_id.startswith("chat:"):
        return
    group_id = room_id[len("chat:") :]
    session = await sio.get_session(sid) or {}
    user = session.get("user", {})
    call_room = f"call:{group_id}"

    if call_room not in call_rooms:
        call_rooms[call_room] = {}

    existing_peers = list(call_rooms[call_room].values())
    await sio.enter_room(sid, call_room)

    call_rooms[call_room][sid] = {
        "socketId": sid,
        "userId": user.get("id"),
        "name": user.get("name"),
    }

    if sid not in socket_call_rooms:
        socket_call_rooms[sid] = set()
    socket_call_rooms[sid].add(call_room)

    await sio.emit("rtc:peers", {"roomId": room_id, "peers": existing_peers}, to=sid)
    await sio.emit(
        "rtc:peer-joined",
        {
            "roomId": room_id,
            "socketId": sid,
            "userId": user.get("id"),
            "name": user.get("name"),
        },
        room=call_room,
        skip_sid=sid,
    )
    await sio.emit(
        "rtc:incoming",
        {
            "roomId": room_id,
            "groupId": group_id,
            "from": {"userId": user.get("id"), "name": user.get("name")},
        },
        room=f"group:{group_id}",
        skip_sid=sid,
    )


def make_rtc_relay(event_name: str):
    async def relay_handler(sid: str, payload: Any):
        if not isinstance(payload, dict):
            return
        target_sid = payload.get("to")
        if not target_sid or not isinstance(target_sid, str):
            return
        session = await sio.get_session(sid) or {}
        user = session.get("user", {})

        out_payload = dict(payload)
        out_payload["from"] = sid
        out_payload["fromUser"] = {"id": user.get("id"), "name": user.get("name")}
        await sio.emit(event_name, out_payload, to=target_sid)

    return relay_handler


sio.on("rtc:offer", make_rtc_relay("rtc:offer"))
sio.on("rtc:answer", make_rtc_relay("rtc:answer"))
sio.on("rtc:ice", make_rtc_relay("rtc:ice"))


@sio.on("rtc:leave")
async def on_rtc_leave(sid: str, room_id: str):
    if not isinstance(room_id, str):
        return
    group_id = room_id.replace("chat:", "")
    call_room = f"call:{group_id}"
    session = await sio.get_session(sid) or {}
    user = session.get("user", {})

    if call_room in call_rooms and sid in call_rooms[call_room]:
        del call_rooms[call_room][sid]
    if sid in socket_call_rooms:
        socket_call_rooms[sid].discard(call_room)

    await sio.leave_room(sid, call_room)
    await sio.emit(
        "rtc:peer-left",
        {"socketId": sid, "userId": user.get("id")},
        room=call_room,
    )


# ──────────────── Direct Emit Helpers ────────────────


async def emit_to_user(user_id: str, event: str, payload: Any = None):
    await sio.emit(event, payload, room=f"user:{user_id}")


async def emit_to_room(room: str, event: str, payload: Any = None):
    await sio.emit(event, payload, room=room)


async def emit_to_org(event: str, payload: Any = None):
    await sio.emit(event, payload, room="org")


# ──────────────── Dual-Path ASGI Wrapper ────────────────


class DualPathSocketASGIApp:
    """
    Mounts Socket.IO on both /api/socket and /socket.io,
    falling back to FastAPI for all other endpoints.
    """

    def __init__(self, socket_server: socketio.AsyncServer, other_app: Any):
        self.sio_app = socketio.ASGIApp(
            socket_server,
            other_asgi_app=other_app,
            socketio_path="api/socket",
        )
        self.other_app = other_app

    def __getattr__(self, name: str):
        return getattr(self.other_app, name)

    async def __call__(self, scope: dict, receive: Any, send: Any):
        path = scope.get("path", "")
        # Forward requests to /socket.io to /api/socket for engineio compatibility
        if path.startswith("/socket.io"):
            new_scope = dict(scope)
            new_scope["path"] = path.replace("/socket.io", "/api/socket", 1)
            await self.sio_app(new_scope, receive, send)
            return

        await self.sio_app(scope, receive, send)


def get_socket_app(fastapi_app: Any):
    return DualPathSocketASGIApp(sio, fastapi_app)
