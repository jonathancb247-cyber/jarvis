"""Non-executing local understanding decision surface.

This module decides whether a local understanding run is an executable
candidate, needs clarification, is refused, or failed closed. It never
executes commands, never calls Runtime or Drivers, and never falls back to a
cloud provider.

The deterministic execution boundary remains authoritative: an
``EXECUTABLE_CANDIDATE`` decision only means that the existing
DeterministicUnderstandingResolver produced a validated plan that would
require the normal confirmation/policy path before any execution. Nothing in
this module executes or side-effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from jarvis_core.ai.contracts import (
    AI_MODEL_NOT_FOUND,
    AI_MODEL_UNAVAILABLE,
    AI_PLAN_REJECTED,
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
    AIActionPlan,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
    PLAN_KINDS,
)
from jarvis_core.ai.gemma_local import GemmaLocalProviderError
from jarvis_core.ai.understanding import normalize_understanding_proposal
from jarvis_core.ai.understanding_resolution import DeterministicUnderstandingResolver
from jarvis_core.ai.validation import AIValidationError, validate_with_planner

EXECUTABLE_CANDIDATE = "executable_candidate"
NEEDS_CLARIFICATION = "needs_clarification"
REFUSED = "refused"
LOCAL_AI_UNAVAILABLE = "local_ai_unavailable"
UNDERSTANDING_FAILED = "understanding_failed"

DECISION_STATUSES = frozenset(
    {
        EXECUTABLE_CANDIDATE,
        NEEDS_CLARIFICATION,
        REFUSED,
        LOCAL_AI_UNAVAILABLE,
        UNDERSTANDING_FAILED,
    }
)

FAILURE_STAGE_PROVIDER_REQUEST = "provider_request"
FAILURE_STAGE_PROPOSAL_NORMALIZATION = "proposal_normalization"
FAILURE_STAGE_RESOLVER = "resolver"
FAILURE_STAGE_FINALIZATION = "finalization"

FAILURE_STAGES = frozenset(
    {
        FAILURE_STAGE_PROVIDER_REQUEST,
        FAILURE_STAGE_PROPOSAL_NORMALIZATION,
        FAILURE_STAGE_RESOLVER,
        FAILURE_STAGE_FINALIZATION,
    }
)

LOCAL_AI_UNAVAILABLE_CODES = frozenset(
    {AI_PROVIDER_UNAVAILABLE, AI_MODEL_NOT_FOUND, AI_MODEL_UNAVAILABLE}
)


@dataclass(frozen=True)
class LocalUnderstandingDecision:
    """Immutable outcome of one non-executing local understanding run."""

    provider_id: str
    model_id: str
    status: str
    proposal_valid: bool = False
    resolver_kind: str | None = None
    planner_kind: str | None = None
    confirmation_required: bool = False
    latency_ms: int | None = None
    failure_stage: str | None = None
    failure_category: str | None = None
    plan: AIActionPlan | None = None
    commands_executed: bool = False

    def __post_init__(self) -> None:
        _require_label(self.provider_id, "provider_id")
        _require_label(self.model_id, "model_id")
        if self.status not in DECISION_STATUSES:
            raise ValueError("decision status is invalid")
        if not isinstance(self.proposal_valid, bool):
            raise ValueError("proposal_valid must be a bool")
        if self.resolver_kind is not None and self.resolver_kind not in PLAN_KINDS:
            raise ValueError("resolver_kind is invalid")
        if self.planner_kind is not None:
            _require_label(self.planner_kind, "planner_kind")
        if not isinstance(self.confirmation_required, bool):
            raise ValueError("confirmation_required must be a bool")
        if self.latency_ms is not None and (
            not isinstance(self.latency_ms, int) or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be None or a non-negative int")
        if self.failure_stage is not None and self.failure_stage not in FAILURE_STAGES:
            raise ValueError("failure_stage is invalid")
        if self.failure_category is not None:
            _require_label(self.failure_category, "failure_category")
        if self.plan is not None and not isinstance(self.plan, AIActionPlan):
            raise ValueError("plan is invalid")
        if self.commands_executed is not False:
            raise ValueError("a local understanding decision never executes commands")
        self._validate_shape()

    def _validate_shape(self) -> None:
        failed = self.status in {LOCAL_AI_UNAVAILABLE, UNDERSTANDING_FAILED}
        if failed:
            if self.plan is not None:
                raise ValueError("failed decisions cannot retain a plan")
            if self.failure_stage is None or self.failure_category is None:
                raise ValueError("failed decisions require a failure stage and category")
        elif self.failure_stage is not None or self.failure_category is not None:
            raise ValueError("non-failed decisions cannot carry failure details")

        if self.status == EXECUTABLE_CANDIDATE:
            if self.plan is None or self.plan.kind != PLAN_KIND_EXECUTE:
                raise ValueError("executable candidates require an execute plan")
            if not self.plan.steps:
                raise ValueError("executable candidates require at least one step")
            if self.resolver_kind != PLAN_KIND_EXECUTE:
                raise ValueError("executable candidates require an execute resolver kind")
            if self.planner_kind is None:
                raise ValueError("executable candidates require a planner kind")
        elif self.status == NEEDS_CLARIFICATION:
            if self.plan is None or self.plan.kind != PLAN_KIND_CLARIFY:
                raise ValueError("needs-clarification requires a clarify plan")
            if self.resolver_kind != PLAN_KIND_CLARIFY:
                raise ValueError("needs-clarification requires a clarify resolver kind")
            if self.planner_kind is not None:
                raise ValueError("non-execute decisions cannot carry a planner kind")
        elif self.status == REFUSED:
            if self.plan is None or self.plan.kind != PLAN_KIND_REFUSE:
                raise ValueError("refused requires a refuse plan")
            if self.resolver_kind != PLAN_KIND_REFUSE:
                raise ValueError("refused requires a refuse resolver kind")
            if self.planner_kind is not None:
                raise ValueError("non-execute decisions cannot carry a planner kind")
        elif self.status == LOCAL_AI_UNAVAILABLE:
            if self.proposal_valid is not False:
                raise ValueError("unavailable local AI retains no proposal")
            if self.resolver_kind is not None or self.planner_kind is not None:
                raise ValueError("unavailable local AI cannot carry plan kinds")
            if self.confirmation_required is not False:
                raise ValueError("unavailable local AI cannot require confirmation")
            if self.failure_category not in LOCAL_AI_UNAVAILABLE_CODES:
                raise ValueError("unavailable local AI requires an unavailable category")
            if self.failure_stage != FAILURE_STAGE_PROVIDER_REQUEST:
                raise ValueError("unavailable local AI requires the provider_request stage")
        elif self.status == UNDERSTANDING_FAILED:
            if self.plan is not None:
                raise ValueError("understanding failures retain no plan")
            if self.proposal_valid is not False:
                raise ValueError("proposal validation failed before resolution")


def decide_understanding(
    provider,
    context,
    *,
    provider_id: str,
    model_id: str,
    resolver: DeterministicUnderstandingResolver | None = None,
    clock: Callable[[], float] = perf_counter,
) -> LocalUnderstandingDecision:
    """Run one non-executing local understanding decision.

    ``provider`` only needs ``extract_understanding(context)``. The existing
    DeterministicUnderstandingResolver and its existing Planner boundary remain
    the sole resolution and planning authority; nothing here executes commands.
    """
    if provider_id is None or not provider_id.strip():
        raise ValueError("provider_id is required")
    if model_id is None or not model_id.strip():
        raise ValueError("model_id is required")
    decision_resolver = resolver or DeterministicUnderstandingResolver()
    started_at = clock()

    refusal = None
    try:
        refusal = decision_resolver.refusal_precheck(context)
    except AIValidationError as error:
        return _fail_closed(
            provider_id,
            model_id,
            FAILURE_STAGE_RESOLVER,
            _safe_code(error),
            started_at,
            clock,
        )
    except Exception:
        return _fail_closed(
            provider_id,
            model_id,
            FAILURE_STAGE_RESOLVER,
            AI_RESPONSE_INVALID,
            started_at,
            clock,
        )

    try:
        raw = provider.extract_understanding(context)
    except GemmaLocalProviderError as error:
        if refusal is not None:
            return _refused(provider_id, model_id, refusal, proposal_valid=False, started_at=started_at, clock=clock)
        return _provider_failure(
            provider_id,
            model_id,
            _safe_code(error),
            started_at,
            clock,
        )
    except Exception:
        if refusal is not None:
            return _refused(provider_id, model_id, refusal, proposal_valid=False, started_at=started_at, clock=clock)
        return _fail_closed(
            provider_id,
            model_id,
            FAILURE_STAGE_PROVIDER_REQUEST,
            AI_RESPONSE_INVALID,
            started_at,
            clock,
        )

    proposal = None
    try:
        proposal = normalize_understanding_proposal(raw)
    except (AIValidationError, TypeError, ValueError) as error:
        if refusal is not None:
            return _refused(provider_id, model_id, refusal, proposal_valid=False, started_at=started_at, clock=clock)
        return _fail_closed(
            provider_id,
            model_id,
            FAILURE_STAGE_PROPOSAL_NORMALIZATION,
            _safe_code_of(error),
            started_at,
            clock,
        )
    except Exception:
        if refusal is not None:
            return _refused(provider_id, model_id, refusal, proposal_valid=False, started_at=started_at, clock=clock)
        return _fail_closed(
            provider_id,
            model_id,
            FAILURE_STAGE_PROPOSAL_NORMALIZATION,
            AI_RESPONSE_INVALID,
            started_at,
            clock,
        )

    if refusal is not None:
        return _refused(
            provider_id,
            model_id,
            refusal,
            proposal_valid=True,
            started_at=started_at,
            clock=clock,
        )

    try:
        plan = decision_resolver.resolve(context, proposal)
    except AIValidationError as error:
        return _fail_closed(
            provider_id,
            model_id,
            FAILURE_STAGE_RESOLVER,
            _safe_code(error),
            started_at,
            clock,
        )
    except Exception:
        return _fail_closed(
            provider_id,
            model_id,
            FAILURE_STAGE_RESOLVER,
            AI_RESPONSE_INVALID,
            started_at,
            clock,
        )

    if plan.kind == PLAN_KIND_EXECUTE:
        try:
            command = validate_with_planner(
                decision_resolver.planner,
                plan.steps[0].canonical_command_text,
            )
            planner_kind = command.name
        except AIValidationError as error:
            return _fail_closed(
                provider_id,
                model_id,
                FAILURE_STAGE_RESOLVER,
                _safe_code(error),
                started_at,
                clock,
            )
        except Exception:
            return _fail_closed(
                provider_id,
                model_id,
                FAILURE_STAGE_RESOLVER,
                AI_RESPONSE_INVALID,
                started_at,
                clock,
            )
        return LocalUnderstandingDecision(
            provider_id=provider_id,
            model_id=model_id,
            status=EXECUTABLE_CANDIDATE,
            proposal_valid=True,
            resolver_kind=PLAN_KIND_EXECUTE,
            planner_kind=planner_kind,
            confirmation_required=plan.confirmation_required,
            latency_ms=_elapsed_ms(started_at, clock),
            plan=plan,
            commands_executed=False,
        )
    if plan.kind == PLAN_KIND_CLARIFY:
        return LocalUnderstandingDecision(
            provider_id=provider_id,
            model_id=model_id,
            status=NEEDS_CLARIFICATION,
            proposal_valid=True,
            resolver_kind=PLAN_KIND_CLARIFY,
            latency_ms=_elapsed_ms(started_at, clock),
            plan=plan,
            commands_executed=False,
        )
    return LocalUnderstandingDecision(
        provider_id=provider_id,
        model_id=model_id,
        status=REFUSED,
        proposal_valid=True,
        resolver_kind=PLAN_KIND_REFUSE,
        latency_ms=_elapsed_ms(started_at, clock),
        plan=plan,
        commands_executed=False,
    )


def _provider_failure(provider_id: str, model_id: str, code: str, started_at: float, clock) -> LocalUnderstandingDecision:
    if code in LOCAL_AI_UNAVAILABLE_CODES:
        return LocalUnderstandingDecision(
            provider_id=provider_id,
            model_id=model_id,
            status=LOCAL_AI_UNAVAILABLE,
            latency_ms=_elapsed_ms(started_at, clock),
            failure_stage=FAILURE_STAGE_PROVIDER_REQUEST,
            failure_category=code,
            commands_executed=False,
        )
    return _fail_closed(
        provider_id,
        model_id,
        FAILURE_STAGE_PROVIDER_REQUEST,
        code,
        started_at,
        clock,
    )


def _fail_closed(provider_id: str, model_id: str, stage: str, code: str, started_at: float, clock) -> LocalUnderstandingDecision:
    return LocalUnderstandingDecision(
        provider_id=provider_id,
        model_id=model_id,
        status=UNDERSTANDING_FAILED,
        latency_ms=_elapsed_ms(started_at, clock),
        failure_stage=stage,
        failure_category=code,
        commands_executed=False,
    )


def _refused(provider_id: str, model_id: str, plan: AIActionPlan, *, proposal_valid: bool, started_at: float, clock) -> LocalUnderstandingDecision:
    return LocalUnderstandingDecision(
        provider_id=provider_id,
        model_id=model_id,
        status=REFUSED,
        proposal_valid=proposal_valid,
        resolver_kind=PLAN_KIND_REFUSE,
        latency_ms=_elapsed_ms(started_at, clock),
        plan=plan,
        commands_executed=False,
    )


def _safe_code(error) -> str:
    code = getattr(error, "code", AI_RESPONSE_INVALID)
    if not isinstance(code, str) or not code.strip():
        return AI_RESPONSE_INVALID
    return code


def _safe_code_of(error) -> str:
    if isinstance(error, AIValidationError):
        return _safe_code(error)
    return AI_RESPONSE_INVALID


def _elapsed_ms(started_at: float, clock) -> int:
    return max(0, round((clock() - started_at) * 1000))


def _require_label(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > 128 or any(ch in value for ch in "\r\n\t"):
        raise ValueError(f"{label} is invalid")


__all__ = [
    "DECISION_STATUSES",
    "EXECUTABLE_CANDIDATE",
    "FAILURE_STAGE_FINALIZATION",
    "FAILURE_STAGE_PROPOSAL_NORMALIZATION",
    "FAILURE_STAGE_PROVIDER_REQUEST",
    "FAILURE_STAGE_RESOLVER",
    "FAILURE_STAGES",
    "LOCAL_AI_UNAVAILABLE",
    "LOCAL_AI_UNAVAILABLE_CODES",
    "LocalUnderstandingDecision",
    "NEEDS_CLARIFICATION",
    "REFUSED",
    "UNDERSTANDING_FAILED",
    "decide_understanding",
]