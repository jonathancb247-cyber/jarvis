"""Fake STT and TTS providers for deterministic voice benchmark scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

from .events import VoiceEvent, VoiceEventKind


class FakeSTTAction(str, Enum):
    PARTIAL = "partial"
    FINAL = "final"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCEL = "cancel"


@dataclass(frozen=True)
class FakeSTTStep:
    action: FakeSTTAction
    transcript: str | None = None
    simulated_time_ms: int = 0
    confidence: float | None = None
    note: str | None = None


class FakeSTTProvider:
    """A scripted STT provider that never accesses microphones or services."""

    def __init__(self, steps: Sequence[FakeSTTStep]):
        self._steps = tuple(steps)

    def events(self) -> tuple[VoiceEvent, ...]:
        events: list[VoiceEvent] = []
        for step in self._steps:
            if step.action is FakeSTTAction.PARTIAL:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.STT_PARTIAL,
                        simulated_time_ms=step.simulated_time_ms,
                        transcript=step.transcript,
                        confidence=step.confidence,
                        note=step.note,
                    )
                )
            elif step.action is FakeSTTAction.FINAL:
                if not step.transcript:
                    events.append(
                        VoiceEvent(
                            VoiceEventKind.STT_ERROR,
                            simulated_time_ms=step.simulated_time_ms,
                            note="invalid_input",
                        )
                    )
                    continue
                events.append(
                    VoiceEvent(
                        VoiceEventKind.STT_FINAL,
                        simulated_time_ms=step.simulated_time_ms,
                        transcript=step.transcript,
                        confidence=step.confidence,
                        note=step.note,
                    )
                )
            elif step.action is FakeSTTAction.ERROR:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.STT_ERROR,
                        simulated_time_ms=step.simulated_time_ms,
                        note=step.note or "provider_error",
                    )
                )
            elif step.action is FakeSTTAction.TIMEOUT:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.STT_TIMEOUT,
                        simulated_time_ms=step.simulated_time_ms,
                        note="timeout",
                    )
                )
            elif step.action is FakeSTTAction.CANCEL:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.STT_CANCELLED,
                        simulated_time_ms=step.simulated_time_ms,
                        note="cancelled",
                    )
                )
        return tuple(events)


class FakeTTSAction(str, Enum):
    START = "start"
    FIRST_AUDIO = "first_audio"
    COMPLETE = "complete"
    INTERRUPT = "interrupt"
    CANCEL = "cancel"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class FakeTTSStep:
    action: FakeTTSAction
    simulated_time_ms: int = 0
    note: str | None = None


class FakeTTSProvider:
    """A scripted TTS provider that never generates or plays audio."""

    def __init__(self, steps: Iterable[FakeTTSStep]):
        self._steps = tuple(steps)

    def events(self, text: str) -> tuple[VoiceEvent, ...]:
        if not text:
            return (
                VoiceEvent(
                    VoiceEventKind.TTS_ERROR,
                    note="invalid_input",
                ),
            )

        events: list[VoiceEvent] = []
        for step in self._steps:
            if step.action is FakeTTSAction.START:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.TTS_STARTED,
                        simulated_time_ms=step.simulated_time_ms,
                        note=step.note,
                    )
                )
            elif step.action is FakeTTSAction.FIRST_AUDIO:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.TTS_FIRST_AUDIO,
                        simulated_time_ms=step.simulated_time_ms,
                        note=step.note,
                    )
                )
            elif step.action is FakeTTSAction.COMPLETE:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.TTS_COMPLETED,
                        simulated_time_ms=step.simulated_time_ms,
                        note=step.note,
                    )
                )
            elif step.action is FakeTTSAction.INTERRUPT:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.TTS_INTERRUPTED,
                        simulated_time_ms=step.simulated_time_ms,
                        note=step.note or "interrupted",
                    )
                )
            elif step.action is FakeTTSAction.CANCEL:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.TTS_CANCELLED,
                        simulated_time_ms=step.simulated_time_ms,
                        note=step.note or "cancelled",
                    )
                )
            elif step.action is FakeTTSAction.ERROR:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.TTS_ERROR,
                        simulated_time_ms=step.simulated_time_ms,
                        note=step.note or "provider_error",
                    )
                )
            elif step.action is FakeTTSAction.TIMEOUT:
                events.append(
                    VoiceEvent(
                        VoiceEventKind.TTS_TIMEOUT,
                        simulated_time_ms=step.simulated_time_ms,
                        note="timeout",
                    )
                )
        return tuple(events)
