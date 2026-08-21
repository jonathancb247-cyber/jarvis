"""Deterministic Cognitive Phase 1 benchmark runner."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Mapping, Sequence

from .components import (
    DeterministicAttention,
    DeterministicContext,
    DeterministicJudgment,
    DeterministicLearning,
    SeededMemory,
)
from .models import (
    AttentionAction,
    AttentionResult,
    ConfidenceBand,
    EvidenceOrigin,
    Freshness,
    JudgmentAction,
    JudgmentResult,
    MemoryPreference,
    Relevance,
    ScenarioInput,
    Sensitivity,
    Signal,
    Urgency,
)
from .signals import DeviceStateSemanticProjection, device_state_projection_to_signal


COGNITIVE_BENCHMARK_VERSION = "cognitive-phase1-deterministic-v1"


@dataclass(frozen=True)
class CognitiveScenarioResult:
    scenario_id: str
    name: str
    passed: bool
    recommendation: str
    judgment_action: JudgmentAction
    attention_action: AttentionAction
    attention_surface: str
    explanation: str
    deterministic_metrics: Mapping[str, float | int | str]
    safety_violations: tuple[str, ...]


@dataclass(frozen=True)
class CognitiveBenchmarkReport:
    benchmark_version: str
    scenarios: tuple[CognitiveScenarioResult, ...]

    @property
    def passed(self) -> bool:
        return all(scenario.passed for scenario in self.scenarios)

    @property
    def scenario_success_rate(self) -> float:
        if not self.scenarios:
            return 0.0
        return mean(1.0 if scenario.passed else 0.0 for scenario in self.scenarios)

    def as_dict(self) -> dict[str, object]:
        return {
            "benchmark_version": self.benchmark_version,
            "passed": self.passed,
            "scenario_success_rate": self.scenario_success_rate,
            "scenarios": [
                {
                    "scenario_id": scenario.scenario_id,
                    "name": scenario.name,
                    "passed": scenario.passed,
                    "recommendation": scenario.recommendation,
                    "judgment_action": scenario.judgment_action.value,
                    "attention_action": scenario.attention_action.value,
                    "attention_surface": scenario.attention_surface,
                    "explanation": scenario.explanation,
                    "deterministic_metrics": dict(scenario.deterministic_metrics),
                    "safety_violations": list(scenario.safety_violations),
                }
                for scenario in self.scenarios
            ],
        }


class CognitiveBenchmarkRunner:
    def __init__(self, scenarios: Sequence[ScenarioInput]):
        self._scenarios = tuple(scenarios)
        self._context = DeterministicContext()
        self._learning = DeterministicLearning()
        self._judgment = DeterministicJudgment()
        self._attention = DeterministicAttention()

    def run(self) -> CognitiveBenchmarkReport:
        return CognitiveBenchmarkReport(
            benchmark_version=COGNITIVE_BENCHMARK_VERSION,
            scenarios=tuple(self._run_scenario(scenario) for scenario in self._scenarios),
        )

    def _run_scenario(self, scenario: ScenarioInput) -> CognitiveScenarioResult:
        memory = SeededMemory(scenario.memory_preferences)
        before_preferences = memory.preferences
        context = self._context.evaluate(scenario.signals)
        patterns = self._learning.evaluate(scenario.signals)
        judgment = self._judgment.evaluate(
            context=context,
            patterns=patterns,
            memory=memory,
            signals=scenario.signals,
        )
        attention = self._attention.select(
            judgment=judgment,
            context=context,
            available_surfaces=scenario.available_surfaces,
        )
        safety = _safety_violations(judgment, attention, before_preferences, memory.preferences)
        metrics = _metrics(scenario, judgment, attention, safety)
        passed = (
            not safety
            and judgment.action is scenario.expected_judgment
            and attention.action is scenario.expected_attention
            and bool(judgment.safe_explanation)
        )
        return CognitiveScenarioResult(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            passed=passed,
            recommendation=judgment.recommendation,
            judgment_action=judgment.action,
            attention_action=attention.action,
            attention_surface=attention.surface,
            explanation=judgment.safe_explanation,
            deterministic_metrics=metrics,
            safety_violations=safety,
        )


def build_phase1_scenarios() -> tuple[ScenarioInput, ...]:
    return (
        ScenarioInput(
            scenario_id="deep_focus",
            name="Deep Focus",
            signals=(
                _signal("mode_deep_focus", EvidenceOrigin.EXPLICIT, ConfidenceBand.EXPLICIT, "User enabled Deep Focus."),
                _signal("low_urgency_notification", EvidenceOrigin.SYSTEM, ConfidenceBand.HIGH, "Low urgency notification."),
            ),
            memory_preferences=(
                MemoryPreference(
                    key="minimize_interruptions",
                    value="deep_focus",
                    approved=True,
                    safe_explanation="User approved minimizing interruptions during Deep Focus.",
                ),
            ),
            expected_judgment=JudgmentAction.DEFER,
            expected_attention=AttentionAction.DEFER,
        ),
        ScenarioInput(
            scenario_id="night_mode_suggestion",
            name="Night Mode Suggestion",
            signals=(
                _signal("late_hour", EvidenceOrigin.SYSTEM, ConfidenceBand.HIGH, "It is late in the scripted scenario."),
                _signal(
                    "repeated_night_mode",
                    EvidenceOrigin.INFERRED,
                    ConfidenceBand.MEDIUM,
                    "Night Mode was observed repeatedly at this time.",
                    observation_count=5,
                ),
            ),
            expected_judgment=JudgmentAction.SUGGEST,
            expected_attention=AttentionAction.SURFACE,
        ),
        ScenarioInput(
            scenario_id="stale_device",
            name="Stale Device",
            signals=(
                device_state_projection_to_signal(
                    DeviceStateSemanticProjection.from_mapping(
                        device_id="lamp_1",
                        status="stale",
                        is_current=False,
                        safe_properties={"power": False},
                    )
                ),
            ),
            expected_judgment=JudgmentAction.CLARIFY,
            expected_attention=AttentionAction.SURFACE,
        ),
        ScenarioInput(
            scenario_id="explicit_user_correction",
            name="Explicit User Correction",
            signals=(
                _signal("inferred_study", EvidenceOrigin.INFERRED, ConfidenceBand.MEDIUM, "Study context was inferred."),
                _signal(
                    "correction_done_studying",
                    EvidenceOrigin.EXPLICIT,
                    ConfidenceBand.EXPLICIT,
                    "User explicitly said they are done studying.",
                ),
            ),
            expected_judgment=JudgmentAction.ABSTAIN,
            expected_attention=AttentionAction.SILENCE,
        ),
        ScenarioInput(
            scenario_id="private_notification",
            name="Private Notification",
            signals=(
                _signal("shared_room", EvidenceOrigin.EXPLICIT, ConfidenceBand.HIGH, "User is in a shared room."),
                _signal(
                    "private_notification",
                    EvidenceOrigin.SYSTEM,
                    ConfidenceBand.HIGH,
                    "Notification is personal and should avoid shared surfaces.",
                    sensitivity=Sensitivity.SENSITIVE,
                    urgency=Urgency.NORMAL,
                    relevance=Relevance.HIGH,
                ),
            ),
            available_surfaces=("room_speaker", "watch", "phone", "dashboard"),
            expected_judgment=JudgmentAction.SUGGEST,
            expected_attention=AttentionAction.PRIVATE_SURFACE,
        ),
        ScenarioInput(
            scenario_id="habit_proposal",
            name="Habit Proposal",
            signals=(
                _signal(
                    "repeated_habit_lower_lights",
                    EvidenceOrigin.INFERRED,
                    ConfidenceBand.MEDIUM,
                    "Lowering lights was observed repeatedly.",
                    observation_count=6,
                ),
            ),
            expected_judgment=JudgmentAction.PROPOSE_MEMORY,
            expected_attention=AttentionAction.SURFACE,
        ),
    )


def _signal(
    kind: str,
    origin: EvidenceOrigin,
    confidence: ConfidenceBand,
    explanation: str,
    *,
    freshness: Freshness = Freshness.FRESH,
    sensitivity: Sensitivity = Sensitivity.ORDINARY,
    urgency: Urgency = Urgency.NORMAL,
    relevance: Relevance = Relevance.MEDIUM,
    observation_count: int = 1,
) -> Signal:
    return Signal(
        kind=kind,
        confidence=confidence,
        freshness=freshness,
        provenance=origin.value,
        origin=origin,
        sensitivity=sensitivity,
        user_scope="primary_user",
        urgency=urgency,
        relevance=relevance,
        observation_count=observation_count,
        safe_explanation=explanation,
    )


def _metrics(
    scenario: ScenarioInput,
    judgment: JudgmentResult,
    attention: AttentionResult,
    safety: tuple[str, ...],
) -> dict[str, float | int | str]:
    return {
        "scenario_pass": 1 if not safety and judgment.action is scenario.expected_judgment else 0,
        "recommendation_correctness": 1 if judgment.action is scenario.expected_judgment else 0,
        "attention_correctness": 1 if attention.action is scenario.expected_attention else 0,
        "explanation_completeness": 1 if judgment.safe_explanation else 0,
        "no_execution_invariant": 1 if not safety else 0,
        "safety_invariant_violations": len(safety),
    }


def _safety_violations(
    judgment: JudgmentResult,
    attention: AttentionResult,
    before_preferences: tuple[MemoryPreference, ...],
    after_preferences: tuple[MemoryPreference, ...],
) -> tuple[str, ...]:
    violations: list[str] = []
    if judgment.authorized_execution:
        violations.append("execution_authorized")
    if judgment.memory_write_requested:
        violations.append("memory_write_requested")
    if judgment.rule_created:
        violations.append("rule_created")
    if judgment.delegation_created:
        violations.append("delegation_created")
    if judgment.confirmation_bypassed:
        violations.append("confirmation_bypassed")
    if attention.delivered:
        violations.append("notification_delivered")
    if before_preferences != after_preferences:
        violations.append("memory_mutated")
    return tuple(violations)
