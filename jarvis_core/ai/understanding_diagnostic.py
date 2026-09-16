"""Safe projections of a LocalUnderstandingDecision for diagnostics and CLI.

This module never logs raw user text, raw model output, or canonical command
text by default. Canonical command text is only included when the caller
explicitly enables ``show_canonical``.
"""

from __future__ import annotations

from typing import Mapping

from jarvis_core.ai.contracts import PLAN_KIND_CLARIFY, PLAN_KIND_EXECUTE, PLAN_KIND_REFUSE
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    LocalUnderstandingDecision,
)


def describe_decision(
    decision: LocalUnderstandingDecision,
    *,
    show_canonical: bool = False,
) -> dict[str, object]:
    """Return a JSON-safe, bounded projection of a decision.

    Canonical command text is hidden unless ``show_canonical`` is explicit.
    Raw user text and raw model output are never included.
    """
    payload: dict[str, object] = {
        "provider_id": decision.provider_id,
        "model_id": decision.model_id,
        "status": decision.status,
        "proposal_valid": decision.proposal_valid,
        "resolver_kind": decision.resolver_kind,
        "planner_kind": decision.planner_kind,
        "confirmation_required": decision.confirmation_required,
        "latency_ms": decision.latency_ms,
        "failure_stage": decision.failure_stage,
        "failure_category": decision.failure_category,
        "commands_executed": decision.commands_executed,
    }
    if decision.plan is None:
        return payload
    if decision.plan.safe_summary:
        payload["safe_summary"] = decision.plan.safe_summary
    if decision.plan.clarification is not None:
        payload["clarification"] = {
            "question": decision.plan.clarification.question,
            "reason_code": decision.plan.clarification.reason_code,
            "missing_fields": list(decision.plan.clarification.missing_fields),
            "candidate_options": list(decision.plan.clarification.candidate_options),
        }
    if decision.plan.refusal is not None:
        payload["refusal"] = {
            "safe_message": decision.plan.refusal.safe_message,
            "reason_code": decision.plan.refusal.reason_code,
        }
    if decision.plan.steps and show_canonical:
        payload["canonical_command_text"] = decision.plan.steps[0].canonical_command_text
        payload["safe_description"] = decision.plan.steps[0].safe_description
    return payload


def format_decision_text(
    decision: LocalUnderstandingDecision,
    *,
    show_canonical: bool = False,
) -> str:
    """Render a concise diagnostic description for a CLI.

    ``commands_executed`` is always rendered as false because a local
    understanding decision can never execute commands.
    """
    lines = [
        f"provider_id: {decision.provider_id}",
        f"model_id: {decision.model_id}",
        f"status: {decision.status}",
        f"proposal_valid: {str(decision.proposal_valid).lower()}",
        f"resolver_kind: {decision.resolver_kind or 'null'}",
        f"planner_kind: {decision.planner_kind or 'null'}",
        f"confirmation_required: {str(decision.confirmation_required).lower()}",
        f"latency_ms: {_optional_int(decision.latency_ms)}",
        f"failure_stage: {decision.failure_stage or 'null'}",
        f"failure_category: {decision.failure_category or 'null'}",
        "commands_executed: false",
    ]
    if decision.plan is not None:
        if decision.plan.safe_summary:
            lines.append(f"safe_summary: {decision.plan.safe_summary}")
        if decision.plan.clarification is not None:
            clarification = decision.plan.clarification
            lines.append(
                "clarification: "
                f"{clarification.question} "
                f"(reason: {clarification.reason_code})"
            )
        if decision.plan.refusal is not None:
            refusal = decision.plan.refusal
            lines.append(
                f"refusal: {refusal.safe_message} (reason: {refusal.reason_code})"
            )
        if decision.plan.steps and show_canonical:
            step = decision.plan.steps[0]
            lines.append(f"canonical_command: {step.canonical_command_text}")
            lines.append(f"safe_description: {step.safe_description}")
    return "\n".join(lines)


def decision_status_label(decision: LocalUnderstandingDecision) -> str:
    """Short human label for the decision surface outcome."""
    if decision.status == EXECUTABLE_CANDIDATE:
        return "validated, non-executing candidate"
    if decision.status == "needs_clarification":
        return "clarification required"
    if decision.status == "refused":
        return "refused"
    if decision.status == "local_ai_unavailable":
        return "local AI unavailable"
    if decision.status == "understanding_failed":
        return "understanding failed closed"
    return decision.status


def plan_kind(decision: LocalUnderstandingDecision) -> str | None:
    """Return the deterministic plan kind when one exists."""
    if decision.plan is None:
        return None
    return decision.plan.kind


def candidate_actions(decision: LocalUnderstandingDecision) -> tuple[Mapping[str, object], ...]:
    """Bounded action metadata for executable candidates only."""
    if decision.status != EXECUTABLE_CANDIDATE or decision.plan is None:
        return ()
    actions = []
    for step in decision.plan.steps:
        actions.append(
            {
                "index": step.index,
                "kind": step.action_kind,
                "uses_command": bool(step.canonical_command_text),
            }
        )
    return tuple(actions)


def describe_execution_state() -> dict[str, object]:
    """Explicit proof that the decision surface performs no execution."""
    return {
        "runtime": False,
        "drivers": False,
        "stt": False,
        "voice": False,
        "cloud_fallback": False,
        "model_router": False,
        "action_execution": False,
    }


def describe_plan_kind_authority(decision: LocalUnderstandingDecision) -> str:
    """Name the deterministic authority that produced the plan, if any."""
    if decision.plan is None:
        return "none"
    if decision.plan.kind == PLAN_KIND_EXECUTE:
        return "DeterministicUnderstandingResolver with existing Planner validation"
    if decision.plan.kind == PLAN_KIND_CLARIFY:
        return "DeterministicUnderstandingResolver"
    if decision.plan.kind == PLAN_KIND_REFUSE:
        return "DeterministicUnderstandingResolver refusal precheck"
    return "unknown"


def _optional_int(value: int | None) -> str:
    if value is None:
        return "null"
    return str(value)


__all__ = [
    "candidate_actions",
    "decision_status_label",
    "describe_decision",
    "describe_execution_state",
    "describe_plan_kind_authority",
    "format_decision_text",
    "plan_kind",
]