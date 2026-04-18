"""
socket_server.py - Socket.IO + CRDT relay runtime for collaborative editing.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import socketio

from app.core.config import settings
from app.db.supabase import supabase
from app.services.code_workspace.collaboration_service import collaboration_service

logger = logging.getLogger(__name__)

DEFAULT_COLORS = [
    "#4F8EF7",
    "#F76E6E",
    "#34C77B",
    "#F7B955",
    "#B46EF7",
    "#52C8D9",
    "#E985DA",
    "#7BB3FF",
]


@dataclass
class _Identity:
    user_id: str
    user_name: str
    color: str


@dataclass
class _Participant:
    sid: str
    user_id: str
    user_name: str
    color: str
    joined_at: float
    last_seen_at: float


@dataclass
class _Room:
    room_id: str
    file_id: str
    project_id: Optional[str]
    owner_user_id: Optional[str]
    participants: Dict[str, _Participant] = field(default_factory=dict)
    awareness_updates: Dict[str, str] = field(default_factory=dict)
    snapshot_update: Optional[str] = None
    updates: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class RealtimeCollaborationHub:
    """In-memory room manager for Socket.IO collaborative CRDT sync."""

    def __init__(self) -> None:
        self._rooms: Dict[str, _Room] = {}
        self._sid_rooms: Dict[str, Set[str]] = {}
        self._sid_identity: Dict[str, _Identity] = {}

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _pick_color(seed: str) -> str:
        digest = hashlib.sha256(str(seed or "anonymous").encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % len(DEFAULT_COLORS)
        return DEFAULT_COLORS[index]

    @staticmethod
    def _normalize_text(value: Optional[str], fallback: str = "") -> str:
        normalized = str(value or "").strip()
        return normalized or str(fallback or "")

    @staticmethod
    def _normalize_room_id(value: Optional[str]) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("roomId is required")
        return normalized[:180]

    @staticmethod
    def _normalize_file_id(value: Optional[str]) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("fileId is required")
        return normalized[:128]

    @staticmethod
    def _trim_update(value: Optional[str]) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("update payload is required")

        max_chars = max(256, int(settings.COLLAB_SOCKET_MAX_BUFFER_BYTES))
        if len(normalized) > max_chars:
            raise ValueError("update payload exceeds max buffer")

        return normalized

    def _prune(self) -> None:
        now = self._now()
        room_ttl = max(300, int(settings.COLLAB_SOCKET_REPLAY_TTL_SECONDS))
        presence_ttl = max(30, int(settings.COLLABORATION_PRESENCE_TTL_SECONDS))

        stale_room_ids: List[str] = []
        for room_id, room in self._rooms.items():
            stale_participants = [
                sid
                for sid, participant in room.participants.items()
                if now - participant.last_seen_at > presence_ttl
            ]
            for sid in stale_participants:
                room.participants.pop(sid, None)
                room.awareness_updates.pop(sid, None)

            if not room.participants and now - room.updated_at > room_ttl:
                stale_room_ids.append(room_id)

        for room_id in stale_room_ids:
            self._rooms.pop(room_id, None)

        max_rooms = max(10, int(settings.COLLABORATION_MAX_WORKSPACES))
        if len(self._rooms) <= max_rooms:
            return

        ranked = sorted(self._rooms.values(), key=lambda room: room.updated_at)
        for room in ranked[: len(self._rooms) - max_rooms]:
            self._rooms.pop(room.room_id, None)

    def _upsert_identity(self, sid: str, user_id: str, user_name: str, color: str) -> None:
        self._sid_identity[sid] = _Identity(
            user_id=self._normalize_text(user_id),
            user_name=self._normalize_text(user_name, user_id),
            color=self._normalize_text(color, self._pick_color(user_id)),
        )

    def _identity_for_sid(self, sid: str) -> Optional[_Identity]:
        return self._sid_identity.get(sid)

    def _room_for_join(
        self,
        *,
        room_id: str,
        file_id: str,
        project_id: Optional[str],
        owner_user_id: Optional[str],
    ) -> _Room:
        room = self._rooms.get(room_id)
        if room:
            return room

        room = _Room(
            room_id=room_id,
            file_id=file_id,
            project_id=project_id,
            owner_user_id=owner_user_id,
        )
        self._rooms[room_id] = room
        return room

    def _validate_room_access(
        self,
        *,
        user_id: str,
        file_id: str,
        project_id: Optional[str],
        owner_user_id: Optional[str],
    ) -> bool:
        if user_id == settings.MOCK_USER_ID:
            return True

        if not supabase:
            return bool(user_id)

        try:
            result = supabase.table("code_files").select("id, user_id").eq("id", file_id).limit(1).execute()
            data = result.data or []
            if not data:
                return False

            file_owner = self._normalize_text(data[0].get("user_id"))
            if not file_owner:
                return False

            if file_owner == user_id:
                return True

            # Owner assertion path: guest collaborators must target the true owner and
            # must already have active presence in the shared collaboration workspace.
            asserted_owner = self._normalize_text(owner_user_id)
            safe_project_id = self._normalize_text(project_id)
            if asserted_owner and asserted_owner == file_owner and safe_project_id:
                return collaboration_service.is_workspace_participant(safe_project_id, user_id)

            return False
        except Exception:
            return user_id == settings.MOCK_USER_ID

    def join_room(
        self,
        *,
        sid: str,
        room_id: str,
        file_id: str,
        project_id: Optional[str],
        owner_user_id: Optional[str],
    ) -> dict:
        self._prune()

        identity = self._identity_for_sid(sid)
        if not identity or not identity.user_id:
            raise ValueError("Unauthorized socket identity")

        safe_room_id = self._normalize_room_id(room_id)
        safe_file_id = self._normalize_file_id(file_id)

        if not self._validate_room_access(
            user_id=identity.user_id,
            file_id=safe_file_id,
            project_id=project_id,
            owner_user_id=owner_user_id,
        ):
            raise PermissionError("User is not authorized for this room")

        room = self._room_for_join(
            room_id=safe_room_id,
            file_id=safe_file_id,
            project_id=self._normalize_text(project_id) or None,
            owner_user_id=self._normalize_text(owner_user_id) or None,
        )

        now = self._now()
        participant = room.participants.get(sid)
        joined_at = participant.joined_at if participant else now
        room.participants[sid] = _Participant(
            sid=sid,
            user_id=identity.user_id,
            user_name=identity.user_name,
            color=identity.color,
            joined_at=joined_at,
            last_seen_at=now,
        )
        room.updated_at = now

        sid_rooms = self._sid_rooms.setdefault(sid, set())
        sid_rooms.add(safe_room_id)

        join_updates = room.updates[-max(1, int(settings.COLLAB_SOCKET_MAX_JOIN_UPDATES)) :]

        return {
            "roomId": room.room_id,
            "fileId": room.file_id,
            "projectId": room.project_id,
            "document": {
                "snapshot": room.snapshot_update,
                "updates": join_updates,
                "hasDocument": bool(room.snapshot_update or join_updates),
            },
            "presence": {
                "users": self.participants_payload(room.room_id),
                "awareness": list(room.awareness_updates.values()),
            },
            "serverTime": int(now * 1000),
        }

    def leave_room(self, sid: str, room_id: Optional[str]) -> Optional[str]:
        identity = self._identity_for_sid(sid)
        if not identity:
            return None

        safe_room_id = self._normalize_text(room_id)
        if not safe_room_id:
            return None

        room = self._rooms.get(safe_room_id)
        if room:
            room.participants.pop(sid, None)
            room.awareness_updates.pop(sid, None)
            room.updated_at = self._now()

        sid_rooms = self._sid_rooms.get(sid)
        if sid_rooms:
            sid_rooms.discard(safe_room_id)
            if not sid_rooms:
                self._sid_rooms.pop(sid, None)

        return safe_room_id

    def remove_sid(self, sid: str) -> List[str]:
        room_ids = sorted(list(self._sid_rooms.get(sid) or []))
        for room_id in room_ids:
            room = self._rooms.get(room_id)
            if room:
                room.participants.pop(sid, None)
                room.awareness_updates.pop(sid, None)
                room.updated_at = self._now()

        self._sid_rooms.pop(sid, None)
        self._sid_identity.pop(sid, None)
        return room_ids

    def touch(self, sid: str) -> None:
        now = self._now()
        for room_id in self._sid_rooms.get(sid) or []:
            room = self._rooms.get(room_id)
            if not room:
                continue
            participant = room.participants.get(sid)
            if participant:
                participant.last_seen_at = now
                room.updated_at = now

    def store_document_updates(
        self,
        *,
        sid: str,
        room_id: str,
        updates: List[str],
        is_snapshot: bool,
    ) -> dict:
        safe_room_id = self._normalize_room_id(room_id)
        room = self._rooms.get(safe_room_id)
        if not room:
            raise ValueError("Room not found")

        identity = self._identity_for_sid(sid)
        if not identity:
            raise ValueError("Unauthorized socket identity")

        safe_updates = [self._trim_update(item) for item in updates if str(item or "").strip()]
        if not safe_updates:
            raise ValueError("No document updates provided")

        if is_snapshot:
            room.snapshot_update = safe_updates[-1]
            room.updates = []
        else:
            room.updates.extend(safe_updates)
            max_updates = max(1, int(settings.COLLAB_SOCKET_MAX_ROOM_UPDATES))
            if len(room.updates) > max_updates:
                room.updates = room.updates[-max_updates:]

        room.updated_at = self._now()

        return {
            "roomId": room.room_id,
            "updates": safe_updates,
            "isSnapshot": bool(is_snapshot),
            "sender": {
                "userId": identity.user_id,
                "userName": identity.user_name,
                "color": identity.color,
            },
            "timestamp": int(room.updated_at * 1000),
        }

    def store_awareness(self, *, sid: str, room_id: str, awareness_update: str) -> dict:
        safe_room_id = self._normalize_room_id(room_id)
        room = self._rooms.get(safe_room_id)
        if not room:
            raise ValueError("Room not found")

        identity = self._identity_for_sid(sid)
        if not identity:
            raise ValueError("Unauthorized socket identity")

        safe_update = self._trim_update(awareness_update)
        room.awareness_updates[sid] = safe_update

        participant = room.participants.get(sid)
        if participant:
            participant.last_seen_at = self._now()

        room.updated_at = self._now()

        return {
            "roomId": room.room_id,
            "update": safe_update,
            "sender": {
                "userId": identity.user_id,
                "userName": identity.user_name,
                "color": identity.color,
            },
            "timestamp": int(room.updated_at * 1000),
        }

    def room_sync_payload(self, room_id: str) -> dict:
        safe_room_id = self._normalize_room_id(room_id)
        room = self._rooms.get(safe_room_id)
        if not room:
            raise ValueError("Room not found")

        updates = room.updates[-max(1, int(settings.COLLAB_SOCKET_MAX_JOIN_UPDATES)) :]
        return {
            "roomId": room.room_id,
            "snapshot": room.snapshot_update,
            "updates": updates,
            "hasDocument": bool(room.snapshot_update or updates),
        }

    def participants_payload(self, room_id: str) -> List[dict]:
        room = self._rooms.get(room_id)
        if not room:
            return []

        values = list(room.participants.values())
        values.sort(key=lambda participant: (participant.user_name.lower(), participant.user_id.lower()))
        return [
            {
                "sid": participant.sid,
                "userId": participant.user_id,
                "userName": participant.user_name,
                "color": participant.color,
                "joinedAt": int(participant.joined_at * 1000),
                "lastSeenAt": int(participant.last_seen_at * 1000),
            }
            for participant in values
        ]


def _socket_cors_origins() -> object:
    origins = settings.get_cors_origins()
    if "*" in origins:
        return "*"
    return origins


hub = RealtimeCollaborationHub()

socket_server = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_socket_cors_origins(),
    logger=False,
    engineio_logger=False,
    ping_interval=20,
    ping_timeout=30,
    max_http_buffer_size=max(1024 * 64, int(settings.COLLAB_SOCKET_MAX_BUFFER_BYTES)),
)

socket_app = socketio.ASGIApp(socket_server, socketio_path="socket.io")


@socket_server.event
async def connect(sid, environ, auth):
    try:
        payload = auth or {}
        user_id = hub._normalize_text(payload.get("userId") if isinstance(payload, dict) else None)
        user_name = hub._normalize_text(payload.get("userName") if isinstance(payload, dict) else None, user_id)
        color = hub._normalize_text(payload.get("color") if isinstance(payload, dict) else None)

        if not user_id:
            raise ConnectionRefusedError("Unauthorized: missing userId")

        if not color:
            color = hub._pick_color(user_id)

        hub._upsert_identity(sid, user_id=user_id, user_name=user_name, color=color)
        await socket_server.emit("socket-ready", {"sid": sid}, to=sid)
    except ConnectionRefusedError:
        raise
    except Exception as exc:
        logger.warning("Socket connect failed: %s", exc)
        raise ConnectionRefusedError("Connection failed")


@socket_server.on("join-room")
async def on_join_room(sid, payload):
    data = payload or {}

    try:
        room = hub.join_room(
            sid=sid,
            room_id=data.get("roomId"),
            file_id=data.get("fileId"),
            project_id=data.get("projectId"),
            owner_user_id=data.get("ownerUserId"),
        )
    except PermissionError as exc:
        await socket_server.emit("room-error", {"roomId": data.get("roomId"), "message": str(exc)}, to=sid)
        return
    except Exception as exc:
        await socket_server.emit(
            "room-error",
            {"roomId": data.get("roomId"), "message": f"Join failed: {str(exc)}"},
            to=sid,
        )
        return

    room_id = room["roomId"]
    await socket_server.enter_room(sid, room_id)
    await socket_server.emit("room-joined", room, to=sid)

    await socket_server.emit(
        "presence-updated",
        {
            "roomId": room_id,
            "users": hub.participants_payload(room_id),
            "timestamp": int(time.time() * 1000),
        },
        room=room_id,
    )


@socket_server.on("leave-room")
async def on_leave_room(sid, payload):
    data = payload or {}
    room_id = hub.leave_room(sid, data.get("roomId"))
    if not room_id:
        return

    await socket_server.leave_room(sid, room_id)
    await socket_server.emit(
        "presence-updated",
        {
            "roomId": room_id,
            "users": hub.participants_payload(room_id),
            "timestamp": int(time.time() * 1000),
        },
        room=room_id,
    )


@socket_server.on("sync-document")
async def on_sync_document(sid, payload):
    data = payload or {}

    updates_payload = data.get("updates")
    if isinstance(updates_payload, list):
        updates = [str(item or "") for item in updates_payload]
    else:
        single = str(data.get("update") or "").strip()
        updates = [single] if single else []

    try:
        event_payload = hub.store_document_updates(
            sid=sid,
            room_id=data.get("roomId"),
            updates=updates,
            is_snapshot=bool(data.get("isSnapshot")),
        )
    except Exception as exc:
        await socket_server.emit(
            "room-error",
            {
                "roomId": data.get("roomId"),
                "message": f"sync-document failed: {str(exc)}",
            },
            to=sid,
        )
        return

    await socket_server.emit("sync-document", event_payload, room=event_payload["roomId"], skip_sid=sid)


@socket_server.on("presence-update")
async def on_presence_update(sid, payload):
    data = payload or {}
    try:
        event_payload = hub.store_awareness(
            sid=sid,
            room_id=data.get("roomId"),
            awareness_update=data.get("update"),
        )
    except Exception as exc:
        await socket_server.emit(
            "room-error",
            {
                "roomId": data.get("roomId"),
                "message": f"presence-update failed: {str(exc)}",
            },
            to=sid,
        )
        return

    await socket_server.emit("presence-update", event_payload, room=event_payload["roomId"], skip_sid=sid)


@socket_server.on("request-sync")
async def on_request_sync(sid, payload):
    data = payload or {}
    try:
        sync_payload = hub.room_sync_payload(data.get("roomId"))
    except Exception as exc:
        await socket_server.emit(
            "room-error",
            {
                "roomId": data.get("roomId"),
                "message": f"request-sync failed: {str(exc)}",
            },
            to=sid,
        )
        return

    await socket_server.emit("sync-recovery", sync_payload, to=sid)


@socket_server.event
async def disconnect(sid):
    room_ids = hub.remove_sid(sid)
    for room_id in room_ids:
        await socket_server.emit(
            "presence-updated",
            {
                "roomId": room_id,
                "users": hub.participants_payload(room_id),
                "timestamp": int(time.time() * 1000),
            },
            room=room_id,
        )
