"""Deterministic cognitive components for Phase 1 scenarios."""

from __future__ import annotations

from .models import (
    AttentionAction,
    AttentionResult,
    ConfidenceBand,
    ContextSnapshot,
    EvidenceOrigin,
    Freshness,
    JudgmentAction,
    JudgmentResult,
    MemoryPreference,
    PatternEvidence,
    Sensitivity,
    Signal,
)


class SeededMemory:
    def __init__(self, preferences: tuple[MemoryPreference, ...] = ()):
        self._preferences = tuple(preference for preference in preferences if preference.approved)

    def find(self, key: str) -> MemoryPreference | None:
        for preference in self._preferences:
            if preference.key == key:
                return preference
        return None

    @property
    def preferences(self) -> tuple[MemoryPreference, ...]:
        return self._preferences


class DeterministicLearning:
    def evaluate(self, signals: tuple[Signal, ...]) -> tuple[PatternEvidence, ...]:
        patterns: list[PatternEvidence] = []
        for signal in signals:
            if signal.kind.startswith("repeated_") and signal.observation_count >= 3:
                patterns.append(
                    PatternEvidence(
                        pattern_id=signal.kind.removeprefix("repeated_"),
                        observation_count=signal.observation_count,
                        confidence=ConfidenceBand.HIGH if signal.observation_count >= 5 else ConfidenceBand.MEDIUM,
                        safe_explanation=signal.safe_explanation
                        or f"Observed {signal.observation_count} matching events.",
                    )
                )
        return tuple(patterns)


class DeterministicContext:
    def evaluate(self, signals: tuple[Signal, ...]) -> ContextSnapshot:
        active_modes: list[str] = []
        hypotheses: list[Signal] = []
        corrections = tuple(signal for signal in signals if signal.kind == "correction_done_studying")
        study_corrected = bool(corrections)

        for signal in signals:
            if signal.freshness is Freshness.EXPIRED:
                continue
            if signal.kind == "mode_deep_focus" and signal.origin is EvidenceOrigin.EXPLICIT:
                active_modes.append("deep_focus")
                hypotheses.append(signal)
            elif signal.kind == "late_hour":
                active_modes.append("late_hour")
                hypotheses.append(signal)
            elif signal.kind == "inferred_study" and not study_corrected:
                active_modes.append("study")
                hypotheses.append(signal)
            elif signal.kind == "shared_room":
                active_modes.append("shared_room")
                hypotheses.append(signal)
            elif signal.kind == "stale_device_state":
                active_modes.append("device_state_stale")
                hypotheses.append(signal)
            elif signal.kind == "unknown_device_state":
                active_modes.append("device_state_unknown")
                hypotheses.append(signal)
            elif signal.kind == "current_device_state":
                active_modes.append("device_state_current")
                hypotheses.append(signal)
            elif signal.kind == "watch_connected":
                active_modes.append("wearable_available")
                active_modes.append("personal_surface_evidence_available")
                active_modes.append("context_evidence_available")
                hypotheses.append(signal)
            elif signal.kind in {"watch_unavailable", "watch_unknown_or_stale"}:
                active_modes.append("wearable_signal_degraded")
                hypotheses.append(signal)

        if study_corrected:
            hypotheses.extend(corrections)

        return ContextSnapshot(
            active_modes=tuple(dict.fromkeys(active_modes)),
            hypotheses=tuple(hypotheses),
            explicit_corrections=corrections,
        )


class DeterministicJudgment:
    def evaluate(
        self,
        *,
        context: ContextSnapshot,
        patterns: tuple[PatternEvidence, ...],
        memory: SeededMemory,
        signals: tuple[Signal, ...],
    ) -> JudgmentResult:
        if context.has_mode("device_state_stale"):
            return JudgmentResult(
                action=JudgmentAction.CLARIFY,
                recommendation="request_explicit_status_read",
                confidence=ConfidenceBand.HIGH,
                safe_explanation="Device state is stale, so a fresh read should be requested before relying on it.",
            )

        if context.has_mode("device_state_unknown"):
            return JudgmentResult(
                action=JudgmentAction.CLARIFY,
                recommendation="request_device_status_evidence",
                confidence=ConfidenceBand.LOW,
                safe_explanation="Device state is unknown, so current physical state should not be assumed.",
            )

        if context.has_mode("wearable_available"):
            return JudgmentResult(
                action=JudgmentAction.SUGGEST,
                recommendation="note_watch_connection_signal_available",
                confidence=ConfidenceBand.MEDIUM,
                safe_explanation=(
                    "Watch connection signal is available as context evidence only; it does not prove user presence or identity."
                ),
            )

        if context.has_mode("wearable_signal_degraded"):
            return JudgmentResult(
                action=JudgmentAction.CLARIFY,
                recommendation="note_wearable_context_confidence_reduced",
                confidence=ConfidenceBand.LOW,
                safe_explanation="Wearable signal is unavailable or stale, so no user context should be inferred from it.",
            )

        if context.explicit_corrections:
            return JudgmentResult(
                action=JudgmentAction.ABSTAIN,
                recommendation="do_not_continue_focus_recommendation",
                confidence=ConfidenceBand.EXPLICIT,
                safe_explanation="Explicit user correction overrides the inferred study context.",
            )

        private_signal = _first_sensitive_notification(signals)
        if private_signal and context.has_mode("shared_room"):
            return JudgmentResult(
                action=JudgmentAction.SUGGEST,
                recommendation="surface_private_notification_privately",
                confidence=ConfidenceBand.HIGH,
                safe_explanation="Sensitive information should avoid shared-room output surfaces.",
            )

        quiet_preference = memory.find("minimize_interruptions")
        low_urgency = any(signal.kind == "low_urgency_notification" for signal in signals)
        if context.has_mode("deep_focus") and low_urgency and quiet_preference:
            return JudgmentResult(
                action=JudgmentAction.DEFER,
                recommendation="defer_low_urgency_notification",
                confidence=ConfidenceBand.HIGH,
                safe_explanation="Deferred because Deep Focus is active and an approved preference minimizes interruptions.",
            )

        if context.has_mode("late_hour") and _has_pattern(patterns, "night_mode"):
            return JudgmentResult(
                action=JudgmentAction.SUGGEST,
                recommendation="suggest_night_mode",
                confidence=ConfidenceBand.MEDIUM,
                safe_explanation="Late-hour context matches a repeated Night Mode pattern.",
            )

        habit_pattern = _first_pattern(patterns, "habit")
        if habit_pattern:
            return JudgmentResult(
                action=JudgmentAction.PROPOSE_MEMORY,
                recommendation="propose_saving_preference",
                confidence=habit_pattern.confidence,
                safe_explanation="A repeated habit can be proposed for approval, but it is not saved automatically.",
            )

        return JudgmentResult(
            action=JudgmentAction.ABSTAIN,
            recommendation="no_recommendation",
            confidence=ConfidenceBand.LOW,
            safe_explanation="No deterministic recommendation is supported by the scenario evidence.",
        )


class DeterministicAttention:
    def select(
        self,
        *,
        judgment: JudgmentResult,
        context: ContextSnapshot,
        available_surfaces: tuple[str, ...],
    ) -> AttentionResult:
        if judgment.action is JudgmentAction.DEFER:
            return AttentionResult(
                action=AttentionAction.DEFER,
                surface="silent",
                delivered=False,
                safe_explanation=judgment.safe_explanation,
            )

        if judgment.recommendation == "surface_private_notification_privately":
            surface = "watch" if "watch" in available_surfaces else "phone" if "phone" in available_surfaces else "silent"
            return AttentionResult(
                action=AttentionAction.PRIVATE_SURFACE,
                surface=surface,
                delivered=False,
                safe_explanation="Selected a private fake surface for sensitive information.",
            )

        if judgment.action in {JudgmentAction.SUGGEST, JudgmentAction.CLARIFY, JudgmentAction.PROPOSE_MEMORY}:
            surface = "dashboard" if "dashboard" in available_surfaces else available_surfaces[0]
            return AttentionResult(
                action=AttentionAction.SURFACE,
                surface=surface,
                delivered=False,
                safe_explanation="Surfaced as a fake recommendation only; no notification was delivered.",
            )

        return AttentionResult(
            action=AttentionAction.SILENCE,
            surface="silent",
            delivered=False,
            safe_explanation="No supported recommendation should be surfaced.",
        )


def _has_pattern(patterns: tuple[PatternEvidence, ...], pattern_id: str) -> bool:
    return any(pattern.pattern_id == pattern_id for pattern in patterns)


def _first_pattern(patterns: tuple[PatternEvidence, ...], prefix: str) -> PatternEvidence | None:
    for pattern in patterns:
        if pattern.pattern_id.startswith(prefix):
            return pattern
    return None


def _first_sensitive_notification(signals: tuple[Signal, ...]) -> Signal | None:
    for signal in signals:
        if signal.kind == "private_notification" and signal.sensitivity in {
            Sensitivity.PERSONAL,
            Sensitivity.SENSITIVE,
            Sensitivity.RESTRICTED,
        }:
            return signal
    return None
