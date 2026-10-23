"""In-memory session management for chat conversations."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    """A single conversation session with stage, collected data, and activity tracking."""

    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    stage: str = "discovery"
    collected: dict[str, Any] = field(default_factory=dict)
    last_active: float = field(default_factory=time.monotonic)


class SessionStore:
    """Keep short-lived chat history for each user session with async-safe access."""

    def __init__(self, idle_timeout_seconds: int = 30 * 60) -> None:
        self.idle_timeout_seconds = idle_timeout_seconds
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def _purge_expired_locked(self, now: float | None = None) -> None:
        """Prune sessions that have been idle beyond the configured timeout."""
        now = now or time.monotonic()
        expired = [
            sid for sid, session in self._sessions.items() if now - session.last_active > self.idle_timeout_seconds
        ]
        for sid in expired:
            self._sessions.pop(sid, None)

    async def create_session(self) -> Session:
        """Return a fresh session record."""
        async with self._lock:
            session_id = str(uuid.uuid4())
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
            return session

    async def get_session(self, session_id: str | None, *, create_if_missing: bool = True) -> Session:
        """Return the current session or create one if it does not exist."""
        async with self._lock:
            now = time.monotonic()
            await self._purge_expired_locked(now)

            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_active = now
                return session

            if not create_if_missing:
                raise KeyError(f"Unknown session: {session_id}")

            resolved_id = session_id or str(uuid.uuid4())
            session = Session(session_id=resolved_id)
            self._sessions[resolved_id] = session
            return session

    async def get_or_create_session(self, session_id: str | None) -> Session:
        """Compatibility helper that returns an existing or newly created session."""
        return await self.get_session(session_id, create_if_missing=True)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and return whether it existed."""
        async with self._lock:
            existed = session_id in self._sessions
            if existed:
                self._sessions.pop(session_id, None)
            return existed

    async def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        """Append a message to the active conversation history."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = Session(session_id=session_id)
                self._sessions[session_id] = session
            session.messages.append(message)
            session.last_active = time.monotonic()

    async def set_stage(self, session_id: str, stage: str) -> None:
        """Update the session’s current conversational stage."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.stage = stage
            session.last_active = time.monotonic()

    async def update_collected(self, session_id: str, values: dict[str, Any]) -> None:
        """Merge newly collected values into the session state."""
        if not values:
            return
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.collected.update({k: v for k, v in values.items() if v not in (None, "")})
            session.last_active = time.monotonic()

    async def prune_history(self, session_id: str, keep_last: int = 20) -> None:
        """Keep the most recent message history while preserving the session context."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            if len(session.messages) > keep_last:
                session.messages = session.messages[-keep_last:]
            session.last_active = time.monotonic()

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Compatibility accessor used by older code paths."""
        session = self._sessions.get(session_id)
        return list(session.messages) if session else []

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Compatibility helper with the older simple message API."""
        message = {"role": role, "content": content}
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        self._sessions[session_id].messages.append(message)
        self._sessions[session_id].last_active = time.monotonic()

    def get_or_create(self, session_id: str | None) -> tuple[str, list[dict[str, Any]]]:
        """Compatibility helper returning a session ID and recent messages."""
        resolved_id = session_id or str(uuid.uuid4())
        if resolved_id not in self._sessions:
            self._sessions[resolved_id] = Session(session_id=resolved_id)
        return resolved_id, list(self._sessions[resolved_id].messages)
