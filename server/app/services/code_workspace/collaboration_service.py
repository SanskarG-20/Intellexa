"""
collaboration_service.py - In-memory real-time collaboration coordination.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.code import (
    CollaborationEvent,
    CollaborationEventType,
    CollaborationJoinResponse,
    CollaborationParticipant,
    CollaborationRole,
    CollaborationStateResponse,
)


@dataclass
class _ParticipantState:
    actor_id: str
    actor_name: str
    actor_role: CollaborationRole
    joined_at: float
    last_seen_at: float


@dataclass
class _EventState:
    sequence: int
    workspace_id: str
    event_type: CollaborationEventType
    actor_id: str
    actor_name: str
    actor_role: CollaborationRole
    timestamp: float
    file_id: Optional[str]
    file_key: Optional[str]
    payload: Dict[str, Any]


@dataclass
class _WorkspaceState:
    workspace_id: str
    next_sequence: int = 1
    participants: Dict[str, _ParticipantState] = field(default_factory=dict)
    events: List[_EventState] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class CollaborationService:
    """Ephemeral workspace collaboration manager used by Code Space APIs."""

    def __init__(self) -> None:
        self._workspaces: Dict[str, _WorkspaceState] = {}

    @staticmethod
    def _now() -> float:
        return time.time()

    @staticmethod
    def _ts_to_datetime(value: float) -> datetime:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    @staticmethod
    def _normalize_workspace_id(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("workspace_id is required")
        return normalized[:128]

    @staticmethod
    def _normalize_actor_id(value: Optional[str]) -> str:
        normalized = str(value or "").strip()
        if normalized:
            return normalized[:128]
        return f"actor-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _normalize_actor_name(value: Optional[str], fallback: str) -> str:
        normalized = str(value or "").strip()
        if normalized:
            return normalized[:120]
        return str(fallback or "Collaborator")[:120]

    @staticmethod
    def _normalize_file_key(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip().replace("\\", "/")
        return normalized[:600] or None

    def _prune(self) -> None:
        now = self._now()
        presence_ttl = max(20, int(settings.COLLABORATION_PRESENCE_TTL_SECONDS))
        workspace_ttl = max(300, int(settings.COLLABORATION_WORKSPACE_TTL_SECONDS))

        stale_workspaces: List[str] = []
        for workspace_id, workspace in self._workspaces.items():
            stale_participants = [
                actor_id
                for actor_id, participant in workspace.participants.items()
                if now - participant.last_seen_at > presence_ttl
            ]
            for actor_id in stale_participants:
                workspace.participants.pop(actor_id, None)

            if not workspace.participants and now - workspace.updated_at > workspace_ttl:
                stale_workspaces.append(workspace_id)

        for workspace_id in stale_workspaces:
            self._workspaces.pop(workspace_id, None)

        max_workspaces = max(10, int(settings.COLLABORATION_MAX_WORKSPACES))
        if len(self._workspaces) <= max_workspaces:
            return

        ranked = sorted(self._workspaces.items(), key=lambda item: item[1].updated_at)
        extra = len(self._workspaces) - max_workspaces
        for workspace_id, _ in ranked[:extra]:
            self._workspaces.pop(workspace_id, None)

    def _ensure_workspace(self, workspace_id: str) -> _WorkspaceState:
        if workspace_id not in self._workspaces:
            self._workspaces[workspace_id] = _WorkspaceState(workspace_id=workspace_id)
        return self._workspaces[workspace_id]

    def is_workspace_participant(self, workspace_id: str, actor_id: str) -> bool:
        """Return True when actor currently has active presence in workspace."""
        try:
            self._prune()
            safe_workspace_id = self._normalize_workspace_id(workspace_id)
            safe_actor_id = self._normalize_actor_id(actor_id)
        except ValueError:
            return False

        workspace = self._workspaces.get(safe_workspace_id)
        if not workspace:
            return False

        return safe_actor_id in workspace.participants

    def _participant_to_schema(self, participant: _ParticipantState) -> CollaborationParticipant:
        return CollaborationParticipant(
            actor_id=participant.actor_id,
            actor_name=participant.actor_name,
            actor_role=participant.actor_role,
            joined_at=self._ts_to_datetime(participant.joined_at),
            last_seen_at=self._ts_to_datetime(participant.last_seen_at),
        )

    def _event_to_schema(self, event: _EventState) -> CollaborationEvent:
        return CollaborationEvent(
            sequence=event.sequence,
            workspace_id=event.workspace_id,
            event_type=event.event_type,
            actor_id=event.actor_id,
            actor_name=event.actor_name,
            actor_role=event.actor_role,
            timestamp=self._ts_to_datetime(event.timestamp),
            file_id=event.file_id,
            file_key=event.file_key,
            payload=dict(event.payload or {}),
        )

    def join_workspace(
        self,
        *,
        workspace_id: str,
        actor_id: Optional[str] = None,
        actor_name: Optional[str] = None,
        actor_role: CollaborationRole = CollaborationRole.USER,
    ) -> CollaborationJoinResponse:
        if not settings.COLLABORATION_ENABLED:
            raise ValueError("Collaboration is disabled")

        self._prune()

        safe_workspace_id = self._normalize_workspace_id(workspace_id)
        safe_actor_id = self._normalize_actor_id(actor_id)
        safe_actor_name = self._normalize_actor_name(actor_name, safe_actor_id)

        workspace = self._ensure_workspace(safe_workspace_id)
        now = self._now()

        existing = workspace.participants.get(safe_actor_id)
        joined_at = existing.joined_at if existing else now
        workspace.participants[safe_actor_id] = _ParticipantState(
            actor_id=safe_actor_id,
            actor_name=safe_actor_name,
            actor_role=actor_role,
            joined_at=joined_at,
            last_seen_at=now,
        )
        workspace.updated_at = now

        participants = [
            self._participant_to_schema(item)
            for item in sorted(workspace.participants.values(), key=lambda p: p.actor_name.lower())
        ]

        return CollaborationJoinResponse(
            workspace_id=safe_workspace_id,
            actor_id=safe_actor_id,
            sequence=max(0, workspace.next_sequence - 1),
            participants=participants,
        )

    def publish_event(
        self,
        *,
        workspace_id: str,
        event_type: CollaborationEventType,
        actor_id: Optional[str],
        actor_name: Optional[str],
        actor_role: CollaborationRole,
        payload: Optional[Dict[str, Any]] = None,
        file_id: Optional[str] = None,
        file_key: Optional[str] = None,
    ) -> CollaborationEvent:
        if not settings.COLLABORATION_ENABLED:
            raise ValueError("Collaboration is disabled")

        self._prune()

        safe_workspace_id = self._normalize_workspace_id(workspace_id)
        safe_actor_id = self._normalize_actor_id(actor_id)
        safe_actor_name = self._normalize_actor_name(actor_name, safe_actor_id)
        safe_file_key = self._normalize_file_key(file_key)

        workspace = self._ensure_workspace(safe_workspace_id)
        now = self._now()

        participant = workspace.participants.get(safe_actor_id)
        if participant is None:
            participant = _ParticipantState(
                actor_id=safe_actor_id,
                actor_name=safe_actor_name,
                actor_role=actor_role,
                joined_at=now,
                last_seen_at=now,
            )
            workspace.participants[safe_actor_id] = participant
        else:
            participant.actor_name = safe_actor_name
            participant.actor_role = actor_role
            participant.last_seen_at = now

        event_state = _EventState(
            sequence=workspace.next_sequence,
            workspace_id=safe_workspace_id,
            event_type=event_type,
            actor_id=safe_actor_id,
            actor_name=safe_actor_name,
            actor_role=actor_role,
            timestamp=now,
            file_id=str(file_id).strip() if file_id else None,
            file_key=safe_file_key,
            payload=dict(payload or {}),
        )

        workspace.next_sequence += 1
        workspace.updated_at = now
        workspace.events.append(event_state)

        max_events = max(20, int(settings.COLLABORATION_MAX_EVENTS_PER_WORKSPACE))
        if len(workspace.events) > max_events:
            workspace.events = workspace.events[-max_events:]

        return self._event_to_schema(event_state)

    def publish_file_sync(
        self,
        *,
        workspace_id: str,
        actor_id: Optional[str],
        actor_name: Optional[str],
        actor_role: CollaborationRole = CollaborationRole.USER,
        file_id: Optional[str],
        file_key: Optional[str],
        filename: str,
        path: str,
        language: str,
        content: str,
        updated_at: str,
    ) -> CollaborationEvent:
        return self.publish_event(
            workspace_id=workspace_id,
            event_type=CollaborationEventType.FILE_SYNC,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=actor_role,
            file_id=file_id,
            file_key=file_key,
            payload={
                "filename": str(filename or "")[:255],
                "path": str(path or "/")[:500],
                "language": str(language or "plaintext")[:50],
                "content": str(content or ""),
                "updated_at": str(updated_at or ""),
            },
        )

    def publish_file_deleted(
        self,
        *,
        workspace_id: str,
        actor_id: Optional[str],
        actor_name: Optional[str],
        file_id: Optional[str],
        file_key: Optional[str],
        filename: str,
        path: str,
    ) -> CollaborationEvent:
        return self.publish_event(
            workspace_id=workspace_id,
            event_type=CollaborationEventType.FILE_DELETED,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=CollaborationRole.USER,
            file_id=file_id,
            file_key=file_key,
            payload={
                "filename": str(filename or "")[:255],
                "path": str(path or "/")[:500],
            },
        )

    def get_state(
        self,
        *,
        workspace_id: str,
        since_sequence: int = 0,
        limit: int = 50,
        actor_id: Optional[str] = None,
        actor_name: Optional[str] = None,
        actor_role: CollaborationRole = CollaborationRole.USER,
    ) -> CollaborationStateResponse:
        if not settings.COLLABORATION_ENABLED:
            raise ValueError("Collaboration is disabled")

        self._prune()

        safe_workspace_id = self._normalize_workspace_id(workspace_id)
        safe_since = max(0, int(since_sequence))
        safe_limit = max(1, min(int(limit), int(settings.COLLABORATION_POLL_MAX_EVENTS)))

        workspace = self._ensure_workspace(safe_workspace_id)
        now = self._now()

        if actor_id:
            safe_actor_id = self._normalize_actor_id(actor_id)
            safe_actor_name = self._normalize_actor_name(actor_name, safe_actor_id)
            participant = workspace.participants.get(safe_actor_id)
            if participant is None:
                participant = _ParticipantState(
                    actor_id=safe_actor_id,
                    actor_name=safe_actor_name,
                    actor_role=actor_role,
                    joined_at=now,
                    last_seen_at=now,
                )
                workspace.participants[safe_actor_id] = participant
            else:
                participant.actor_name = safe_actor_name
                participant.actor_role = actor_role
                participant.last_seen_at = now
            workspace.updated_at = now

        events = [
            self._event_to_schema(item)
            for item in workspace.events
            if item.sequence > safe_since
        ]
        events = events[:safe_limit]

        participants = [
            self._participant_to_schema(item)
            for item in sorted(workspace.participants.values(), key=lambda p: p.actor_name.lower())
        ]

        return CollaborationStateResponse(
            workspace_id=safe_workspace_id,
            sequence=max(0, workspace.next_sequence - 1),
            participants=participants,
            events=events,
        )


collaboration_service = CollaborationService()
