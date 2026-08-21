"""Local deterministic report rendering for the cognitive benchmark."""

from __future__ import annotations

import json
from typing import Iterable

from .benchmark import CognitiveBenchmarkReport, CognitiveScenarioResult


FORBIDDEN_REPORT_TERMS = (
    "action queued",
    "action scheduled",
    "executed",
    "device changed",
    "notification sent",
    "rule created",
    "memory saved",
    "delegation granted",
)

_SAFETY_LABELS = {
    "execution_authorized": "execution_authority_violation",
    "memory_write_requested": "memory_write_boundary_violation",
    "rule_created": "rule_promotion_boundary_violation",
    "delegation_created": "delegation_boundary_violation",
    "confirmation_bypassed": "confirmation_boundary_violation",
    "notification_delivered": "notification_delivery_boundary_violation",
    "memory_mutated": "memory_mutation_boundary_violation",
}


class CognitiveReportRenderer:
    """Renders Phase 1 cognitive reports for local diagnostic inspection."""

    def render_text(self, report: CognitiveBenchmarkReport) -> str:
        lines = [
            "JarvisOS Cognitive Report",
            f"version: {report.benchmark_version}",
            f"passed: {_bool(report.passed)}",
            f"scenario_success_rate: {report.scenario_success_rate:.3f}",
            "",
        ]
        for scenario in report.scenarios:
            lines.extend(_scenario_text_lines(scenario))
            lines.append("")
        rendered = "\n".join(lines).rstrip() + "\n"
        _assert_safe_language(rendered)
        return rendered

    def render_json(self, report: CognitiveBenchmarkReport) -> str:
        payload = {
            "benchmark_version": report.benchmark_version,
            "passed": report.passed,
            "scenario_success_rate": _rounded(report.scenario_success_rate),
            "scenarios": [_scenario_payload(scenario) for scenario in report.scenarios],
        }
        rendered = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        _assert_safe_language(rendered)
        return rendered


def _scenario_text_lines(scenario: CognitiveScenarioResult) -> list[str]:
    status = "PASS" if scenario.passed else "FAIL"
    violations = _safe_violations(scenario.safety_violations)
    return [
        f"- {scenario.name} [{status}]",
        f"  scenario_id: {scenario.scenario_id}",
        f"  recommendation: {scenario.recommendation}",
        f"  judgment: {scenario.judgment_action.value}",
        f"  attention: {scenario.attention_action.value} on {scenario.attention_surface}",
        f"  explanation: {scenario.explanation}",
        f"  safety_invariant_violations: {_format_violations(violations)}",
    ]


def _scenario_payload(scenario: CognitiveScenarioResult) -> dict[str, object]:
    return {
        "attention_action": scenario.attention_action.value,
        "attention_surface": scenario.attention_surface,
        "explanation": scenario.explanation,
        "judgment_action": scenario.judgment_action.value,
        "passed": scenario.passed,
        "recommendation": scenario.recommendation,
        "safety_invariant_violations": list(_safe_violations(scenario.safety_violations)),
        "scenario_id": scenario.scenario_id,
        "scenario_name": scenario.name,
    }


def _safe_violations(violations: Iterable[str]) -> tuple[str, ...]:
    return tuple(_SAFETY_LABELS.get(violation, f"unknown_safety_violation:{violation}") for violation in violations)


def _format_violations(violations: tuple[str, ...]) -> str:
    if not violations:
        return "none"
    return ", ".join(violations)


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _rounded(value: float) -> float:
    return round(value, 3)


def _assert_safe_language(text: str) -> None:
    lower = text.lower()
    for term in FORBIDDEN_REPORT_TERMS:
        if term in lower:
            raise ValueError(f"Unsafe cognitive report wording: {term}")
