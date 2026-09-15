"""Per-model comparison for local understanding/extraction candidates.

This evaluation layer grades local understanding candidates over the exact
same fixture set, prompt contract and DeterministicUnderstandingResolver used
by the understanding role bake-off. Model output remains hint-only and
untrusted. Nothing here executes Runtime, Drivers, tools, STT, Voice, or a
cloud fallback.

The report is lab evidence only: the [model] string is a label recorded for
the run, never a runtime selection. There is no model router or selector.

Android JSON rejection counting relies on an observation hook inside
jarvis_core.ai.gemma_android_bridge: every bridge response (2xx and errors)
may be passed out as a bounded (status, raw_body) record. A transport failure
of 500 with body {"error": "invalid_generation" | "empty_generation"} is
counted as an Android JSON rejection; any other error status is a transport
failure and does not change the escape/validity counts (the provider fails
closed either way).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Mapping, Sequence

from jarvis_core.ai.contracts import PLAN_KIND_EXECUTE
from jarvis_core.ai.understanding_bakeoff import (
    UnderstandingEvaluationResult,
    UnderstandingFixture,
    UnderstandingRoleBakeOff,
    build_default_understanding_fixtures,
)

ANDROID_JSON_REJECTION_STATUS = 500
ANDROID_JSON_REJECTION_CODES = ("invalid_generation", "empty_generation")


@dataclass(frozen=True)
class ServerResponseRecord:
    """Bounded observation of one bridge response (lab hook, no secrets)."""

    http_status: int | None = None
    error_code: str | None = None
    body_size_bytes: int | None = None
    body_excerpt: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "http_status": self.http_status,
            "error_code": self.error_code,
            "body_size_bytes": self.body_size_bytes,
            "body_excerpt": self.body_excerpt,
        }

    @classmethod
    def from_raw(cls, status: int | None, raw: bytes | None) -> "ServerResponseRecord":
        if raw is None:
            return cls(http_status=status, body_size_bytes=None)
        decoded = None
        error_code = None
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = None
        if decoded is not None:
            try:
                parsed = json.loads(decoded)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                value = parsed.get("error")
                if isinstance(value, str):
                    error_code = value
        excerpt = (decoded or "").strip()[:160] or None
        return cls(
            http_status=status,
            error_code=error_code,
            body_size_bytes=len(raw),
            body_excerpt=excerpt,
        )


def is_android_json_rejection(record: ServerResponseRecord) -> bool:
    if record.http_status != ANDROID_JSON_REJECTION_STATUS:
        return False
    return record.error_code in ANDROID_JSON_REJECTION_CODES


def is_unsafe_execute_escape(
    expected_resolver_kind: str | None,
    final_plan_kind: str | None,
) -> bool:
    """True only when an unknown/unsafe expectation still produced execute."""
    if expected_resolver_kind == PLAN_KIND_EXECUTE or final_plan_kind != PLAN_KIND_EXECUTE:
        return False
    return True


@dataclass(frozen=True)
class ModelComparisonFixtureOutcome:
    fixture_id: str
    proposal_valid: float
    intent_accuracy: float
    device_id_accuracy: float
    device_text_accuracy: float
    capability_accuracy: float
    operation_accuracy: float
    argument_accuracy: float
    resolver_kind_accuracy: float
    canonical_command_accuracy: float
    expected_resolver_kind: str
    final_plan_kind: str | None
    canonical_command_text: str | None
    validation_status: str
    normalized_failure: str | None
    unsafe_execute_escape: bool
    cold_or_warm: str
    latency_ms: int | None
    server_response: ServerResponseRecord | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "proposal_valid": self.proposal_valid,
            "intent_accuracy": self.intent_accuracy,
            "device_id_accuracy": self.device_id_accuracy,
            "device_text_accuracy": self.device_text_accuracy,
            "capability_accuracy": self.capability_accuracy,
            "operation_accuracy": self.operation_accuracy,
            "argument_accuracy": self.argument_accuracy,
            "resolver_kind_accuracy": self.resolver_kind_accuracy,
            "canonical_command_accuracy": self.canonical_command_accuracy,
            "expected_resolver_kind": self.expected_resolver_kind,
            "final_plan_kind": self.final_plan_kind,
            "canonical_command_text": self.canonical_command_text,
            "validation_status": self.validation_status,
            "normalized_failure": self.normalized_failure,
            "unsafe_execute_escape": self.unsafe_execute_escape,
            "cold_or_warm": self.cold_or_warm,
            "latency_ms": self.latency_ms,
            "server_response": (
                self.server_response.as_dict() if self.server_response is not None else None
            ),
        }


@dataclass(frozen=True)
class UnderstandingModelRecord:
    model: str
    fixture_count: int
    valid_proposal_count: int
    invalid_proposal_count: int
    resolved_plan_count: int
    failure_count: int
    android_json_rejection_count: int
    unsafe_execute_escapes: int
    unsafe_execute_escape_fixtures: tuple[str, ...]
    intent_accuracy: float
    device_id_accuracy: float
    device_text_accuracy: float
    device_resolution_accuracy: float
    capability_accuracy: float
    operation_accuracy: float
    argument_accuracy: float
    resolver_kind_accuracy: float
    canonical_command_accuracy: float
    average_latency_ms: float | None
    cold_latency_ms: float | None
    warm_latency_ms: float | None
    memory_rss_mb: float | None
    outcomes: tuple[ModelComparisonFixtureOutcome, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "fixture_count": self.fixture_count,
            "valid_proposal_count": self.valid_proposal_count,
            "invalid_proposal_count": self.invalid_proposal_count,
            "resolved_plan_count": self.resolved_plan_count,
            "failure_count": self.failure_count,
            "android_json_rejection_count": self.android_json_rejection_count,
            "unsafe_execute_escapes": self.unsafe_execute_escapes,
            "unsafe_execute_escape_fixtures": list(self.unsafe_execute_escape_fixtures),
            "intent_accuracy": self.intent_accuracy,
            "device_id_accuracy": self.device_id_accuracy,
            "device_text_accuracy": self.device_text_accuracy,
            "device_resolution_accuracy": self.device_resolution_accuracy,
            "capability_accuracy": self.capability_accuracy,
            "operation_accuracy": self.operation_accuracy,
            "argument_accuracy": self.argument_accuracy,
            "resolver_kind_accuracy": self.resolver_kind_accuracy,
            "canonical_command_accuracy": self.canonical_command_accuracy,
            "average_latency_ms": self.average_latency_ms,
            "cold_latency_ms": self.cold_latency_ms,
            "warm_latency_ms": self.warm_latency_ms,
            "memory_rss_mb": self.memory_rss_mb,
            "outcomes": [outcome.as_dict() for outcome in self.outcomes],
        }


@dataclass(frozen=True)
class UnderstandingModelComparisonReport:
    fixture_set: str
    baseline_model: str
    models: tuple[str, ...]
    records: tuple[UnderstandingModelRecord, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "models", tuple(self.models))
        object.__setattr__(self, "records", tuple(self.records))
        if not self.baseline_model.strip():
            raise ValueError("baseline_model is required")

    def as_dict(self) -> dict[str, object]:
        return {
            "fixture_set": self.fixture_set,
            "baseline_model": self.baseline_model,
            "models": list(self.models),
            "model_count": len(self.records),
            "execution": {
                "runtime": False,
                "drivers": False,
                "stt": False,
                "voice": False,
                "action_execution": False,
                "cloud_fallback": False,
                "model_router": False,
            },
            "records": [record.as_dict() for record in self.records],
        }


def run_understanding_model_comparison(
    providers: Mapping[str, object],
    *,
    fixture_set: str = "ai-understanding-role-bakeoff",
    baseline_model: str,
    fixtures: tuple[UnderstandingFixture, ...] | None = None,
    resolver=None,
    clock: Callable[[], float] | None = None,
    on_fixture: Callable[[str, int, int, UnderstandingEvaluationResult], None] | None = None,
    server_records: (
        Mapping[str, Sequence[ServerResponseRecord] | Callable[[], Sequence[ServerResponseRecord]]]
        | None
    ) = None,
    memory_rss_mb: Mapping[str, float | None] | None = None,
) -> UnderstandingModelComparisonReport:
    if not providers:
        raise ValueError("at least one candidate model provider is required")
    if baseline_model not in providers:
        raise ValueError("baseline_model must match one of the candidate providers")
    eval_fixtures = tuple(fixtures or build_default_understanding_fixtures())
    fixture_records = dict(server_records) if server_records else {}
    memory = dict(memory_rss_mb) if memory_rss_mb else {}

    records = []
    for model, provider in providers.items():
        bakeoff = UnderstandingRoleBakeOff(
            provider,
            provider_name=model,
            fixtures=eval_fixtures,
            resolver=resolver,
            clock=clock,
        )
        results = bakeoff.run()
        observed = _resolve_record_source(fixture_records.get(model, ()))
        outcomes = tuple(
            _outcome(fixture, result, index, observed[index] if index < len(observed) else None)
            for index, (fixture, result) in enumerate(zip(eval_fixtures, results))
        )
        if on_fixture is not None:
            for index, result in enumerate(results, start=1):
                on_fixture(model, index, len(results), result)
        records.append(_record(model, outcomes, memory.get(model)))
    return UnderstandingModelComparisonReport(
        fixture_set=fixture_set,
        baseline_model=baseline_model,
        models=tuple(providers.keys()),
        records=tuple(records),
    )


def _resolve_record_source(
    source: Sequence[ServerResponseRecord] | Callable[[], Sequence[ServerResponseRecord]],
) -> tuple[ServerResponseRecord, ...]:
    return tuple(source() if callable(source) else source)


def _outcome(
    fixture: UnderstandingFixture,
    result: UnderstandingEvaluationResult,
    index: int,
    server_record: ServerResponseRecord | None,
) -> ModelComparisonFixtureOutcome:
    expected_kind = fixture.expectation.resolver_kind
    return ModelComparisonFixtureOutcome(
        fixture_id=fixture.fixture_id,
        proposal_valid=result.metrics.proposal_valid,
        intent_accuracy=result.metrics.intent_accuracy,
        device_id_accuracy=result.metrics.device_id_accuracy,
        device_text_accuracy=result.metrics.device_text_accuracy,
        capability_accuracy=result.metrics.capability_accuracy,
        operation_accuracy=result.metrics.operation_accuracy,
        argument_accuracy=result.metrics.argument_accuracy,
        resolver_kind_accuracy=result.metrics.resolver_kind_accuracy,
        canonical_command_accuracy=result.metrics.canonical_command_accuracy,
        expected_resolver_kind=expected_kind,
        final_plan_kind=result.final_plan_kind,
        canonical_command_text=result.canonical_command_text,
        validation_status=result.validation_status,
        normalized_failure=result.normalized_failure,
        unsafe_execute_escape=is_unsafe_execute_escape(
            expected_kind,
            result.final_plan_kind,
        ),
        cold_or_warm="cold" if index == 0 else "warm",
        latency_ms=result.latency_ms,
        server_response=server_record,
    )


def _record(
    model: str,
    outcomes: tuple[ModelComparisonFixtureOutcome, ...],
    memory_rss_mb: float | None,
) -> UnderstandingModelRecord:
    def mean(attribute: str) -> float:
        if not outcomes:
            return 0.0
        return sum(getattr(outcome, attribute) for outcome in outcomes) / len(outcomes)

    latencies = [outcome.latency_ms for outcome in outcomes if outcome.latency_ms is not None]
    escapes = tuple(
        outcome.fixture_id for outcome in outcomes if outcome.unsafe_execute_escape
    )
    return UnderstandingModelRecord(
        model=model,
        fixture_count=len(outcomes),
        valid_proposal_count=sum(
            1 for outcome in outcomes if outcome.proposal_valid == 1.0
        ),
        invalid_proposal_count=sum(
            1 for outcome in outcomes if outcome.validation_status == "invalid"
        ),
        resolved_plan_count=sum(
            1 for outcome in outcomes if outcome.validation_status == "valid"
        ),
        failure_count=sum(
            1 for outcome in outcomes if outcome.normalized_failure is not None
        ),
        android_json_rejection_count=sum(
            1
            for outcome in outcomes
            if outcome.server_response is not None
            and is_android_json_rejection(outcome.server_response)
        ),
        unsafe_execute_escapes=len(escapes),
        unsafe_execute_escape_fixtures=escapes,
        intent_accuracy=mean("intent_accuracy"),
        device_id_accuracy=mean("device_id_accuracy"),
        device_text_accuracy=mean("device_text_accuracy"),
        device_resolution_accuracy=(mean("device_id_accuracy") + mean("device_text_accuracy")) / 2,
        capability_accuracy=mean("capability_accuracy"),
        operation_accuracy=mean("operation_accuracy"),
        argument_accuracy=mean("argument_accuracy"),
        resolver_kind_accuracy=mean("resolver_kind_accuracy"),
        canonical_command_accuracy=mean("canonical_command_accuracy"),
        average_latency_ms=_rounded_mean(latencies),
        cold_latency_ms=float(latencies[0]) if latencies else None,
        warm_latency_ms=(
            _rounded_mean(latencies[1:]) if len(latencies) > 1 else None
        ),
        memory_rss_mb=memory_rss_mb,
        outcomes=outcomes,
    )


def _rounded_mean(values: Sequence[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


__all__ = [
    "ANDROID_JSON_REJECTION_CODES",
    "ANDROID_JSON_REJECTION_STATUS",
    "ModelComparisonFixtureOutcome",
    "ServerResponseRecord",
    "UnderstandingModelComparisonReport",
    "UnderstandingModelRecord",
    "is_android_json_rejection",
    "is_unsafe_execute_escape",
    "run_understanding_model_comparison",
]