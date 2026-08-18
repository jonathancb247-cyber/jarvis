"""Provider-neutral fake voice events used by the benchmark harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class VoiceEventKind(str, Enum):
    SPEECH_STARTED = "speech_started"
    SPEECH_ENDED = "speech_ended"
    STT_PARTIAL = "stt_partial"
    STT_FINAL = "stt_final"
    STT_ERROR = "stt_error"
    STT_TIMEOUT = "stt_timeout"
    STT_CANCELLED = "stt_cancelled"
    TURN_ACCEPTED = "turn_accepted"
    CLARIFICATION_REQUIRED = "clarification_required"
    CONFIRMATION_PENDING = "confirmation_pending"
    CONFIRMATION_REJECTED = "confirmation_rejected"
    TTS_STARTED = "tts_started"
    TTS_FIRST_AUDIO = "tts_first_audio"
    TTS_INTERRUPTED = "tts_interrupted"
    TTS_COMPLETED = "tts_completed"
    TTS_ERROR = "tts_error"
    TTS_TIMEOUT = "tts_timeout"
    TTS_CANCELLED = "tts_cancelled"
    SESSION_EXPIRED = "session_expired"
    SESSION_RESET = "session_reset"


@dataclass(frozen=True)
class VoiceEvent:
    kind: VoiceEventKind
    simulated_time_ms: int = 0
    transcript: str | None = None
    confidence: float | None = None
    note: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.simulated_time_ms < 0:
            raise ValueError("simulated_time_ms must be non-negative")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
