"""Minimal turn manager for deterministic voice benchmark scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .events import VoiceEvent, VoiceEventKind


class TurnState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    ENGAGED = "engaged"
    ASSISTANT_SPEAKING = "assistant_speaking"
    INTERRUPTED = "interrupted"


@dataclass
class TurnManager:
    state: TurnState = TurnState.IDLE
    final_transcripts_accepted: int = 0
    partial_transcripts_seen: int = 0

    def handle(self, event: VoiceEvent) -> VoiceEvent | None:
        if event.kind is VoiceEventKind.SPEECH_STARTED:
            self.state = TurnState.LISTENING
            return None
        if event.kind is VoiceEventKind.STT_PARTIAL:
            self.partial_transcripts_seen += 1
            return None
        if event.kind is VoiceEventKind.STT_FINAL:
            self.final_transcripts_accepted += 1
            self.state = TurnState.ENGAGED
            return VoiceEvent(
                VoiceEventKind.TURN_ACCEPTED,
                simulated_time_ms=event.simulated_time_ms,
                transcript=event.transcript,
            )
        if event.kind is VoiceEventKind.TTS_STARTED:
            self.state = TurnState.ASSISTANT_SPEAKING
            return None
        if event.kind is VoiceEventKind.TTS_INTERRUPTED:
            self.state = TurnState.INTERRUPTED
            return None
        if event.kind in {VoiceEventKind.TTS_COMPLETED, VoiceEventKind.TTS_CANCELLED}:
            self.state = TurnState.ENGAGED
            return None
        return None
