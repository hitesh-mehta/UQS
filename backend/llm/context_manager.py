"""
Per-user LLM Context Manager.
Stores session history, role-scoped schema, and use-case context per user.
This is what the LLM 'knows' about the user's data environment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from backend.core.rbac import format_schema_for_llm, get_role_schema


# ── Session Message ───────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str   # "user" | "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── User Session ──────────────────────────────────────────────────────────────

@dataclass
class UserSession:
    user_id: str
    role: str
    email: str
    session_id: str
    schema_str: str = ""                  # Role-scoped schema as formatted string
    use_case_context: str = ""            # E.g. "NatWest retail banking data"
    conversation_history: list[Message] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    MAX_HISTORY_MESSAGES = 20             # Keep last 20 exchanges in context window

    def add_message(self, role: str, content: str) -> None:
        self.conversation_history.append(Message(role=role, content=content))
        # Trim history to avoid context overflow
        if len(self.conversation_history) > self.MAX_HISTORY_MESSAGES:
            self.conversation_history = self.conversation_history[-self.MAX_HISTORY_MESSAGES:]
        self.last_active = datetime.now(timezone.utc).isoformat()

    def get_history_str(self) -> str:
        """Format conversation history for LLM context injection."""
        lines = []
        for msg in self.conversation_history[-6:]:  # Last 3 exchanges in prompt
            prefix = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{prefix}: {msg.content}")
        return "\n".join(lines)


# ── Session Store ─────────────────────────────────────────────────────────────

class SessionStore:
    """
    In-memory per-user session store.
    In production this would be backed by Redis for horizontal scaling.
    """

    def __init__(self):
        self._sessions: dict[str, UserSession] = {}

    async def get_or_create(
        self,
        user_id: str,
        role: str,
        email: str,
        session_id: str,
        use_case_context: str = "enterprise data analytics platform",
    ) -> UserSession:
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.last_active = datetime.now(timezone.utc).isoformat()
            return session

        # New session — load role-scoped schema from DB
        schema_list = await get_role_schema(role)
        schema_str = format_schema_for_llm(schema_list)

        session = UserSession(
            user_id=user_id,
            role=role,
            email=email,
            session_id=session_id,
            schema_str=schema_str,
            use_case_context=use_case_context,
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[UserSession]:
        return self._sessions.get(session_id)

    def invalidate(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def invalidate_user_sessions(self, user_id: str) -> None:
        to_delete = [k for k, v in self._sessions.items() if v.user_id == user_id]
        for k in to_delete:
            del self._sessions[k]

    def active_session_count(self) -> int:
        return len(self._sessions)


# ── Global singleton ──────────────────────────────────────────────────────────
session_store = SessionStore()
