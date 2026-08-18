"""Deterministic Voice Experience Benchmark harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import mean
from typing import Callable, Mapping, Sequence

from .events import VoiceEvent, VoiceEventKind
from .fakes import (
    FakeSTTAction,
    FakeSTTProvider,
    FakeSTTStep,
    FakeTTSAction,
    FakeTTSProvider,
    FakeTTSStep,
)
from .session import ConversationSession
from .turns import TurnManager


BENCHMARK_VERSION = "voice-phase1-fake-v1"


class IntentOutcome(str, Enum):
    COMMAND = "command"
    CLARIFICATION = "clarification"
    CONFIRMATION_PENDING = "confirmation_pending"
    CONFIRMATION_REJECTED = "confirmation_rejected"
    NO_EXECUTION = "no_execution"
    FAILURE = "failure"


@dataclass(frozen=True)
class FakeIntentResult:
    outcome: IntentOutcome
    spoken_text: str | None = None
    human_facing_device_name: str | None = None
    confirmation_id: str | None = None
    executed: bool = False
    safety_violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkScenario:
    scenario_id: str
    name: str
    stt_steps: tuple[FakeSTTStep, ...]
    tts_steps: tuple[FakeTTSStep, ...]
    intent: Callable[[str, ConversationSession], FakeIntentResult]
    expected_transitions: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkScenarioResult:
    scenario_id: str
    name: str
    passed: bool
    simulated_metrics: Mapping[str, float | int | str]
    safety_violations: tuple[str, ...]
    expected_transitions: tuple[str, ...]
    actual_transitions: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class BenchmarkReport:
    benchmark_version: str
    scenarios: tuple[BenchmarkScenarioResult, ...]

    @property
    def passed(self) -> bool:
        return all(scenario.passed for scenario in self.scenarios)

    @property
    def task_success_rate(self) -> float:
        if not self.scenarios:
            return 0.0
        return mean(1.0 if scenario.passed else 0.0 for scenario in self.scenarios)

    def as_dict(self) -> dict[str, object]:
        return {
            "benchmark_version": self.benchmark_version,
            "passed": self.passed,
            "task_success_rate": self.task_success_rate,
            "scenarios": [
                {
                    "scenario_id": scenario.scenario_id,
                    "name": scenario.name,
                    "passed": scenario.passed,
                    "simulated_metrics": dict(scenario.simulated_metrics),
                    "safety_violations": list(scenario.safety_violations),
                    "expected_transitions": list(scenario.expected_transitions),
                    "actual_transitions": list(scenario.actual_transitions),
                    "notes": scenario.notes,
                }
                for scenario in self.scenarios
            ],
        }


@dataclass
class ScenarioRuntime:
    session: ConversationSession = field(default_factory=ConversationSession)
    turn_manager: TurnManager = field(default_factory=TurnManager)
    driver_reached: bool = False
    physical_mutation_attempted: bool = False
    transcript_persisted: bool = False
    device_state_mutated_by_voice_failure: bool = False
    partial_transcript_interpreted: bool = False
    confirmation_bypassed: bool = False
    internal_id_spoken: bool = False

    def safety_violations(self) -> tuple[str, ...]:
        violations: list[str] = []
        if self.driver_reached:
            violations.append("real_driver_reached")
        if self.physical_mutation_attempted:
            violations.append("physical_mutation_attempted")
        if self.partial_transcript_interpreted:
            violations.append("partial_transcript_execution")
        if self.confirmation_bypassed:
            violations.append("confirmation_bypass")
        if self.transcript_persisted or self.session.persisted_transcripts:
            violations.append("transcript_persistence")
        if self.device_state_mutated_by_voice_failure:
            violations.append("device_state_mutated_by_voice_failure")
        if self.internal_id_spoken:
            violations.append("internal_id_spoken")
        return tuple(violations)


class VoiceBenchmarkRunner:
    def __init__(self, scenarios: Sequence[BenchmarkScenario]):
        self._scenarios = tuple(scenarios)

    def run(self) -> BenchmarkReport:
        return BenchmarkReport(
            benchmark_version=BENCHMARK_VERSION,
            scenarios=tuple(self._run_scenario(scenario) for scenario in self._scenarios),
        )

    def _run_scenario(self, scenario: BenchmarkScenario) -> BenchmarkScenarioResult:
        runtime = ScenarioRuntime()
        events: list[VoiceEvent] = [
            VoiceEvent(VoiceEventKind.SPEECH_STARTED),
            VoiceEvent(VoiceEventKind.SPEECH_ENDED, simulated_time_ms=25),
        ]
        events.extend(FakeSTTProvider(scenario.stt_steps).events())

        final_transcript: str | None = None
        intent_result: FakeIntentResult | None = None
        actual_transitions: list[str] = []

        for event in events:
            actual_transitions.append(event.kind.value)
            accepted = runtime.turn_manager.handle(event)
            if accepted is not None:
                actual_transitions.append(accepted.kind.value)
                final_transcript = accepted.transcript
            if event.kind is VoiceEventKind.STT_PARTIAL:
                # Deliberately observe but never interpret partial speech.
                continue

        if final_transcript is not None:
            runtime.session.remember_turn(final_transcript)
            intent_result = scenario.intent(final_transcript, runtime.session)
            actual_transitions.extend(_intent_transitions(intent_result))
            if intent_result.human_facing_device_name:
                runtime.session.set_reference(intent_result.human_facing_device_name)
            if intent_result.confirmation_id:
                runtime.session.set_pending_confirmation(intent_result.confirmation_id)
            if intent_result.executed:
                runtime.confirmation_bypassed = True
            if _contains_internal_device_id(intent_result.spoken_text):
                runtime.internal_id_spoken = True

        spoken_text = intent_result.spoken_text if intent_result else "No pude procesarlo."
        tts_events = FakeTTSProvider(scenario.tts_steps).events(spoken_text or "")
        for event in tts_events:
            actual_transitions.append(event.kind.value)
            runtime.turn_manager.handle(event)

        safety = runtime.safety_violations()
        if intent_result:
            safety = tuple(dict.fromkeys((*safety, *intent_result.safety_violations)))

        metrics = _metrics(events, tts_events, runtime, intent_result)
        passed = not safety and _scenario_expectations_met(scenario, actual_transitions, intent_result)
        return BenchmarkScenarioResult(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            passed=passed,
            simulated_metrics=metrics,
            safety_violations=safety,
            expected_transitions=scenario.expected_transitions,
            actual_transitions=tuple(actual_transitions),
            notes=scenario.notes,
        )


def build_phase1_scenarios() -> tuple[BenchmarkScenario, ...]:
    return (
        _scenario("normal_command", "normal command", "enciende la lámpara", _command_intent),
        _scenario("follow_up", "follow-up without repeated wake word", "apágala", _follow_up_intent),
        _scenario(
            "partial_then_final",
            "partial STT then final STT",
            "enciende la lámpara",
            _command_intent,
            partial="enciende la",
        ),
        _scenario("partial_safety", "partial STT cannot execute", "enciende la lámpara", _command_intent, partial="enciende"),
        _scenario("cancellation", "cancellation", "cancela", _cancel_intent),
        _scenario("confirmation_rejected", "pending confirmation rejection", "no", _reject_confirmation_intent),
        _scenario("unrelated_si", "unrelated si does not confirm", "sí, claro", _unrelated_yes_intent),
        _scenario("barge_in", "barge-in TTS interruption lifecycle", "para", _cancel_intent, interrupted=True),
        _scenario("ambiguous_reference", "ambiguous reference clarification", "la otra también", _ambiguous_reference_intent),
        _scenario("ambiguous_addressing", "ambiguous addressing no execution", "enciende esa luz", _no_execution_intent),
        _scenario("stt_failure", "STT failure", "", _failure_intent, stt_action=FakeSTTAction.ERROR),
        _scenario("tts_failure", "TTS failure", "estado de la lámpara", _command_intent, tts_action=FakeTTSAction.ERROR),
        _scenario("provider_timeout", "provider timeout unavailable behavior", "", _failure_intent, stt_action=FakeSTTAction.TIMEOUT),
        _scenario("no_persistence", "no automatic persistence", "recuerda esto solo por ahora", _command_intent),
        _scenario("session_expiry", "session reset and expiry", "gracias", _expire_intent),
        _scenario("human_name", "human-facing device name", "lee la lámpara", _human_name_intent),
        _scenario("no_physical_mutation", "no real physical mutation", "enciende la lámpara", _confirmation_intent),
    )


def _scenario(
    scenario_id: str,
    name: str,
    transcript: str,
    intent: Callable[[str, ConversationSession], FakeIntentResult],
    *,
    partial: str | None = None,
    interrupted: bool = False,
    stt_action: FakeSTTAction = FakeSTTAction.FINAL,
    tts_action: FakeTTSAction = FakeTTSAction.COMPLETE,
) -> BenchmarkScenario:
    stt_steps: list[FakeSTTStep] = []
    if partial:
        stt_steps.append(FakeSTTStep(FakeSTTAction.PARTIAL, partial, simulated_time_ms=60, confidence=0.4))
    if stt_action is FakeSTTAction.FINAL:
        stt_steps.append(FakeSTTStep(FakeSTTAction.FINAL, transcript, simulated_time_ms=120, confidence=0.92))
    else:
        stt_steps.append(FakeSTTStep(stt_action, simulated_time_ms=120))

    tts_steps = [
        FakeTTSStep(FakeTTSAction.START, simulated_time_ms=150),
        FakeTTSStep(FakeTTSAction.FIRST_AUDIO, simulated_time_ms=180),
    ]
    if interrupted:
        tts_steps.append(FakeTTSStep(FakeTTSAction.INTERRUPT, simulated_time_ms=210))
    elif tts_action is FakeTTSAction.COMPLETE:
        tts_steps.append(FakeTTSStep(FakeTTSAction.COMPLETE, simulated_time_ms=260))
    else:
        tts_steps.append(FakeTTSStep(tts_action, simulated_time_ms=260))

    return BenchmarkScenario(
        scenario_id=scenario_id,
        name=name,
        stt_steps=tuple(stt_steps),
        tts_steps=tuple(tts_steps),
        intent=intent,
    )


def _command_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    return FakeIntentResult(
        IntentOutcome.COMMAND,
        spoken_text="Listo, usaré la lámpara.",
        human_facing_device_name="la lámpara",
    )


def _follow_up_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    session.set_reference("la lámpara")
    resolved = session.resolve_reference(transcript) or "la lámpara"
    return FakeIntentResult(
        IntentOutcome.COMMAND,
        spoken_text=f"Entendido, sigo con {resolved}.",
        human_facing_device_name=resolved,
    )


def _cancel_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    session.cancel()
    return FakeIntentResult(IntentOutcome.NO_EXECUTION, spoken_text="Cancelado.")


def _reject_confirmation_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    session.set_pending_confirmation("pending-1")
    session.reject_confirmation()
    return FakeIntentResult(IntentOutcome.CONFIRMATION_REJECTED, spoken_text="No ejecuto la acción.")


def _unrelated_yes_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    return FakeIntentResult(IntentOutcome.NO_EXECUTION, spoken_text="No hay una acción pendiente.")


def _ambiguous_reference_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    session.require_clarification()
    return FakeIntentResult(IntentOutcome.CLARIFICATION, spoken_text="¿A cuál dispositivo te refieres?")


def _no_execution_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    return FakeIntentResult(IntentOutcome.NO_EXECUTION, spoken_text="No tomaré eso como una orden.")


def _failure_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    return FakeIntentResult(IntentOutcome.FAILURE, spoken_text="No pude procesar la solicitud.")


def _expire_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    session.expire()
    return FakeIntentResult(IntentOutcome.NO_EXECUTION, spoken_text="Cierro la sesión.")


def _human_name_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    return FakeIntentResult(
        IntentOutcome.COMMAND,
        spoken_text="La lámpara está lista para revisión.",
        human_facing_device_name="la lámpara",
    )


def _confirmation_intent(transcript: str, session: ConversationSession) -> FakeIntentResult:
    return FakeIntentResult(
        IntentOutcome.CONFIRMATION_PENDING,
        spoken_text="Necesito confirmación para encender la lámpara.",
        human_facing_device_name="la lámpara",
        confirmation_id="pending-1",
    )


def _intent_transitions(intent_result: FakeIntentResult) -> tuple[str, ...]:
    if intent_result.outcome is IntentOutcome.CLARIFICATION:
        return (VoiceEventKind.CLARIFICATION_REQUIRED.value,)
    if intent_result.outcome is IntentOutcome.CONFIRMATION_PENDING:
        return (VoiceEventKind.CONFIRMATION_PENDING.value,)
    if intent_result.outcome is IntentOutcome.CONFIRMATION_REJECTED:
        return (VoiceEventKind.CONFIRMATION_REJECTED.value,)
    return ()


def _metrics(
    stt_events: Sequence[VoiceEvent],
    tts_events: Sequence[VoiceEvent],
    runtime: ScenarioRuntime,
    intent_result: FakeIntentResult | None,
) -> dict[str, float | int | str]:
    final_events = [event for event in stt_events if event.kind is VoiceEventKind.STT_FINAL]
    first_audio_events = [event for event in tts_events if event.kind is VoiceEventKind.TTS_FIRST_AUDIO]
    interrupted_events = [event for event in tts_events if event.kind is VoiceEventKind.TTS_INTERRUPTED]
    endpoint_events = [event for event in stt_events if event.kind is VoiceEventKind.SPEECH_ENDED]

    endpoint_time = endpoint_events[-1].simulated_time_ms if endpoint_events else 0
    final_time = final_events[-1].simulated_time_ms if final_events else 0
    first_audio_time = first_audio_events[-1].simulated_time_ms if first_audio_events else 0
    interruption_time = interrupted_events[-1].simulated_time_ms if interrupted_events else 0

    return {
        "latency_kind": "simulated",
        "scenario_success": 1 if intent_result is not None else 0,
        "scripted_intent_accuracy": 1 if intent_result and not intent_result.safety_violations else 0,
        "clarification_success": 1 if intent_result and intent_result.outcome is IntentOutcome.CLARIFICATION else 0,
        "confirmation_rejection_success": 1 if intent_result and intent_result.outcome is IntentOutcome.CONFIRMATION_REJECTED else 0,
        "partial_transcript_safety": 1 if runtime.turn_manager.final_transcripts_accepted <= 1 and not runtime.partial_transcript_interpreted else 0,
        "simulated_endpoint_to_final_latency_ms": max(0, final_time - endpoint_time),
        "simulated_response_to_first_audio_latency_ms": first_audio_time,
        "simulated_barge_in_latency_ms": interruption_time,
        "session_continuity": 1 if runtime.session.state.value != "inactive" else 0,
        "safety_invariant_violations": len(runtime.safety_violations()),
    }


def _scenario_expectations_met(
    scenario: BenchmarkScenario,
    actual_transitions: Sequence[str],
    intent_result: FakeIntentResult | None,
) -> bool:
    if scenario.scenario_id in {"stt_failure", "provider_timeout"}:
        return intent_result is None
    if scenario.scenario_id == "tts_failure":
        return VoiceEventKind.TTS_ERROR.value in actual_transitions
    if scenario.scenario_id == "barge_in":
        return VoiceEventKind.TTS_INTERRUPTED.value in actual_transitions
    if scenario.scenario_id == "session_expiry":
        return intent_result is not None
    return intent_result is not None


def _contains_internal_device_id(text: str | None) -> bool:
    if not text:
        return False
    return "lamp_1" in text or "device_id" in text
