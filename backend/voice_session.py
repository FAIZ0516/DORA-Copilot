"""Voice-session state, registry and the typed events on the wire.

A browser WebSocket cannot send the ``X-Development-Session`` header the rest
of the API authenticates with. Rather than weaken that, an authenticated HTTP
POST mints a short-lived opaque token that is bound server-side to the caller's
identity and conversation; the socket then carries only that token. The token
is meaningless elsewhere, expires on its own, and is invalidated when the
session ends -- no API key or durable secret ever reaches the browser.

The event models live here rather than in ``schemas.py`` because they are the
socket's internal protocol, not the public HTTP contract; the HTTP contracts
for opening a session do live in ``schemas.py``.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .config import settings

# Opaque, unguessable, and short-lived. 32 bytes of urlsafe randomness.
TOKEN_BYTES = 32


class VoiceState(str, Enum):
    """Where a session is. Transitions are enforced by ``can_transition``."""

    IDLE = "idle"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    ASSISTANT_SPEAKING = "assistant_speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    CLOSED = "closed"


# A turn runs listening -> speaking -> transcribing -> thinking -> speaking and
# back. Interruption can happen from any active state, which is the point of
# the feature, so it is reachable from everywhere except a finished session.
_ALLOWED: dict[VoiceState, set[VoiceState]] = {
    VoiceState.IDLE: {VoiceState.LISTENING, VoiceState.ERROR, VoiceState.CLOSED},
    VoiceState.LISTENING: {
        VoiceState.USER_SPEAKING,
        VoiceState.ASSISTANT_SPEAKING,
        VoiceState.THINKING,
        VoiceState.ERROR,
        VoiceState.CLOSED,
    },
    VoiceState.USER_SPEAKING: {
        VoiceState.TRANSCRIBING,
        VoiceState.LISTENING,
        VoiceState.ERROR,
        VoiceState.CLOSED,
    },
    VoiceState.TRANSCRIBING: {
        VoiceState.THINKING,
        VoiceState.LISTENING,
        VoiceState.INTERRUPTED,
        VoiceState.ERROR,
        VoiceState.CLOSED,
    },
    VoiceState.THINKING: {
        VoiceState.ASSISTANT_SPEAKING,
        VoiceState.LISTENING,
        VoiceState.INTERRUPTED,
        VoiceState.ERROR,
        VoiceState.CLOSED,
    },
    VoiceState.ASSISTANT_SPEAKING: {
        VoiceState.LISTENING,
        VoiceState.USER_SPEAKING,
        VoiceState.INTERRUPTED,
        VoiceState.ERROR,
        VoiceState.CLOSED,
    },
    VoiceState.INTERRUPTED: {
        VoiceState.LISTENING,
        VoiceState.USER_SPEAKING,
        VoiceState.ERROR,
        VoiceState.CLOSED,
    },
    VoiceState.ERROR: {VoiceState.LISTENING, VoiceState.CLOSED},
    VoiceState.CLOSED: set(),
}


def can_transition(current: VoiceState, target: VoiceState) -> bool:
    return target in _ALLOWED[current]


# --------------------------------------------------------------------------- #
# Wire events                                                                 #
# --------------------------------------------------------------------------- #


class ClientEvent(BaseModel):
    """Anything the browser may send as JSON. Audio arrives as binary frames."""

    type: Literal[
        "session.start",
        "user.speech_started",
        "user.speech_ended",
        "response.cancel",
        "session.stop",
    ]
    # Which assistant response the client is cancelling, so a late cancel for an
    # already-finished turn cannot kill the next one.
    turn_id: str | None = Field(default=None, max_length=64)


class ServerEvent(BaseModel):
    type: Literal[
        "session.ready",
        "state",
        "transcript.partial",
        "transcript.final",
        "assistant.thinking",
        "assistant.text",
        "assistant.audio_started",
        "assistant.audio_finished",
        "assistant.interrupted",
        "error",
    ]
    state: VoiceState | None = None
    turn_id: str | None = None
    text: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    # Charts and tables travel as the same structures the text chat renders.
    chart: dict[str, Any] | None = None
    table: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    detail: str | None = None
    recoverable: bool = True

    def dumps(self) -> str:
        return self.model_dump_json(exclude_none=True)


# --------------------------------------------------------------------------- #
# Registry                                                                    #
# --------------------------------------------------------------------------- #


@dataclass
class VoiceSession:
    token: str
    user_id: str
    conversation_id: UUID | None
    workspace: str
    project_key: str | None
    dashboard_context: dict[str, Any]
    created_at: float
    expires_at: float
    state: VoiceState = VoiceState.IDLE
    # Incremented per assistant response so a cancel names the turn it means.
    turn: int = 0
    # The turn currently being answered. The socket loop reads this to know what
    # a barge-in should cancel; it used to guess the id before starting the
    # turn, which broke as soon as turns stopped being strictly sequential.
    active_turn: str | None = None
    # Set when the user interrupts; the in-flight turn checks it and discards
    # its own result rather than speaking a stale answer.
    cancelled_turns: set[str] = field(default_factory=set)

    def expired(self, *, now: float | None = None) -> bool:
        return (now or time.monotonic()) >= self.expires_at

    def next_turn_id(self) -> str:
        self.turn += 1
        return f"{self.token[:8]}-{self.turn}"

    def cancel(self, turn_id: str | None) -> None:
        if turn_id:
            self.cancelled_turns.add(turn_id)

    def is_cancelled(self, turn_id: str) -> bool:
        return turn_id in self.cancelled_turns

    def transition(self, target: VoiceState) -> bool:
        if not can_transition(self.state, target):
            return False
        self.state = target
        return True


class VoiceSessionRegistry:
    """In-process store of live voice sessions, keyed by opaque token.

    In-process is the right scope here: a voice session is bound to one open
    socket on one worker, so there is nothing to share and nothing to persist.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, VoiceSession] = {}

    def create(
        self,
        *,
        user_id: str,
        conversation_id: UUID | None,
        workspace: str = "technical",
        project_key: str | None = None,
        dashboard_context: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> VoiceSession:
        self.purge_expired()
        now = time.monotonic()
        ttl = ttl_seconds or settings.voice_session_ttl_seconds
        session = VoiceSession(
            token=secrets.token_urlsafe(TOKEN_BYTES),
            user_id=user_id,
            conversation_id=conversation_id,
            workspace=workspace,
            project_key=project_key,
            dashboard_context=dashboard_context or {},
            created_at=now,
            expires_at=now + ttl,
        )
        self._sessions[session.token] = session
        return session

    def get(self, token: str) -> VoiceSession | None:
        """Return a live session, dropping it if its time is up."""

        session = self._sessions.get(token)
        if session is None:
            return None
        if session.expired():
            self.close(token)
            return None
        return session

    def close(self, token: str) -> None:
        session = self._sessions.pop(token, None)
        if session is not None:
            session.state = VoiceState.CLOSED

    def purge_expired(self, *, now: float | None = None) -> int:
        current = now or time.monotonic()
        stale = [token for token, s in self._sessions.items() if s.expires_at <= current]
        for token in stale:
            self.close(token)
        return len(stale)

    def __len__(self) -> int:
        return len(self._sessions)


registry = VoiceSessionRegistry()


def origin_allowed(origin: str | None) -> bool:
    """Check a WebSocket Origin against the configured CORS origins.

    Browsers do not apply CORS to WebSockets, so this is the only thing
    stopping another site from opening a socket with a stolen token. A missing
    Origin is rejected: every real browser sends one.
    """

    if not origin:
        return False
    allowed = {value.strip().rstrip("/") for value in settings.cors_origin_list if value.strip()}
    if "*" in allowed:
        return True
    return origin.strip().rstrip("/") in allowed


__all__ = [
    "ClientEvent",
    "ServerEvent",
    "VoiceSession",
    "VoiceSessionRegistry",
    "VoiceState",
    "can_transition",
    "origin_allowed",
    "registry",
]
