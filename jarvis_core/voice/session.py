"""Minimal in-memory conversation session support for voice benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SessionState(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXPIRED = "expired"


@dataclass
class ConversationSession:
    """Bounded, non-persistent session state for fake voice scenarios."""

    max_turns: int = 4
    state: SessionState = SessionState.INACTIVE
    turns: list[str] = field(default_factory=list)
    reference: str | None = None
    pending_confirmation_id: str | None = None
    persisted_transcripts: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.state = SessionState.ACTIVE

    def remember_turn(self, transcript: str) -> None:
        if self.state is SessionState.INACTIVE:
            self.start()
        self.turns.append(transcript)
        if len(self.turns) > self.max_turns:
            self.expire()

    def set_reference(self, human_facing_name: str) -> None:
        self.reference = human_facing_name

    def resolve_reference(self, phrase: str) -> str | None:
        if self.state in {SessionState.EXPIRED, SessionState.INACTIVE}:
            return None
        normalized = phrase.lower()
        if any(token in normalized for token in ("la", "lo", "tambien", "también")):
            return self.reference
        return None

    def require_clarification(self) -> None:
        self.state = SessionState.AWAITING_CLARIFICATION

    def set_pending_confirmation(self, confirmation_id: str) -> None:
        self.pending_confirmation_id = confirmation_id
        self.state = SessionState.AWAITING_CONFIRMATION

    def reject_confirmation(self) -> str | None:
        rejected = self.pending_confirmation_id
        self.pending_confirmation_id = None
        self.state = SessionState.ACTIVE
        return rejected

    def cancel(self) -> None:
        self.pending_confirmation_id = None
        self.state = SessionState.ACTIVE

    def expire(self) -> None:
        self.state = SessionState.EXPIRED
        self.reference = None
        self.pending_confirmation_id = None

    def reset(self) -> None:
        self.state = SessionState.INACTIVE
        self.turns.clear()
        self.reference = None
        self.pending_confirmation_id = None
