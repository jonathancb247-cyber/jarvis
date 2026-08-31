"""Deterministic bilingual semantic/tool evaluation for voice bake-offs."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .provider_contracts import (
    ProviderFailure,
    ProviderIdentity,
)


class ConceptualTool(str, Enum):
    DEVICE_POWER = "device_power"
    OPEN_SETTINGS = "open_settings"
    SHOW_MAP = "show_map"
    CALENDAR_CREATE_EVENT = "calendar_create_event"


class SemanticOutcomeTag(str, Enum):
    ENGLISH_PASS_SPANISH_FAIL = "english_pass_spanish_fail"
    SPANISH_TRANSCRIPT_PASS_TOOL_FAIL = "spanish_transcript_pass_tool_fail"
    RELATIVE_DATETIME_NOT_NORMALIZED = "relative_datetime_not_normalized"
    MACHINE_FORMATTED_CLARIFICATION_REQUESTED = (
        "machine_formatted_clarification_requested"
    )
    CLARIFICATION_NEEDED = "clarification_needed"
    CLARIFICATION_UNNECESSARY = "clarification_unnecessary"


@dataclass(frozen=True)
class SemanticExpectation:
    intent: str
    tool: ConceptualTool
    arguments: Mapping[str, str]
    relative_datetime: str | None = None
    clarification_required: bool = False

    def __post_init__(self) -> None:
        if not self.intent.strip():
            raise ValueError("intent is required")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class BilingualSemanticFixture:
    fixture_id: str
    pair_id: str
    language: str
    utterance: str
    expectation: SemanticExpectation

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if not self.pair_id.strip():
            raise ValueError("pair_id is required")
        if self.language not in {"en-US", "es-MX"}:
            raise ValueError("language must be en-US or es-MX")
        if not self.utterance.strip():
            raise ValueError("utterance is required")


@dataclass(frozen=True)
class DownstreamSemanticOutput:
    transcript: str
    intent: str | None = None
    tool: ConceptualTool | None = None
    arguments: Mapping[str, str] = field(default_factory=dict)
    relative_datetime: str | None = None
    clarification_requested: bool = False
    clarification_prompt: str | None = None
    simulated_latency_ms: int | None = None
    failure: ProviderFailure | None = None

    def __post_init__(self) -> None:
        if not self.transcript.strip():
            raise ValueError("transcript is required")
        if self.simulated_latency_ms is not None and self.simulated_latency_ms < 0:
            raise ValueError("simulated_latency_ms must be non-negative")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True)
class DownstreamSemanticScores:
    stt_transcription_accuracy: float
    intent_accuracy: float
    tool_selection_accuracy: float
    argument_extraction_accuracy: float
    relative_datetime_normalization: float
    clarification_quality: float
    end_to_end_task_success: float

    def as_dict(self) -> dict[str, float]:
        return {
            "stt_transcription_accuracy": self.stt_transcription_accuracy,
            "intent_accuracy": self.intent_accuracy,
            "tool_selection_accuracy": self.tool_selection_accuracy,
            "argument_extraction_accuracy": self.argument_extraction_accuracy,
            "relative_datetime_normalization": self.relative_datetime_normalization,
            "clarification_quality": self.clarification_quality,
            "end_to_end_task_success": self.end_to_end_task_success,
        }


@dataclass(frozen=True)
class DownstreamSemanticEvaluationResult:
    provider: ProviderIdentity
    fixture_id: str
    pair_id: str
    language: str
    expected_tool: ConceptualTool
    observed_tool: ConceptualTool | None
    scores: DownstreamSemanticScores
    outcome_tags: tuple[SemanticOutcomeTag, ...] = ()
    simulated_latency_ms: int | None = None
    failure: ProviderFailure | None = None

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if not self.pair_id.strip():
            raise ValueError("pair_id is required")
        if self.simulated_latency_ms is not None and self.simulated_latency_ms < 0:
            raise ValueError("simulated_latency_ms must be non-negative")

    def as_dict(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "pair_id": self.pair_id,
            "language": self.language,
            "expected_tool": self.expected_tool.value,
            "observed_tool": self.observed_tool.value if self.observed_tool else None,
            "scores": self.scores.as_dict(),
            "outcome_tags": [tag.value for tag in self.outcome_tags],
            "simulated_latency_ms": self.simulated_latency_ms,
            "failure": self.failure.category.value if self.failure else None,
        }


def build_bilingual_semantic_fixtures() -> tuple[BilingualSemanticFixture, ...]:
    return (
        BilingualSemanticFixture(
            fixture_id="semantic_flashlight_en",
            pair_id="flashlight_power",
            language="en-US",
            utterance="turn on the flashlight",
            expectation=SemanticExpectation(
                intent="turn_on_light",
                tool=ConceptualTool.DEVICE_POWER,
                arguments={"target": "flashlight", "state": "on"},
            ),
        ),
        BilingualSemanticFixture(
            fixture_id="semantic_flashlight_es",
            pair_id="flashlight_power",
            language="es-MX",
            utterance="enciende la linterna",
            expectation=SemanticExpectation(
                intent="turn_on_light",
                tool=ConceptualTool.DEVICE_POWER,
                arguments={"target": "flashlight", "state": "on"},
            ),
        ),
        BilingualSemanticFixture(
            fixture_id="semantic_wifi_settings_en",
            pair_id="wifi_settings",
            language="en-US",
            utterance="open Wi-Fi settings",
            expectation=SemanticExpectation(
                intent="open_settings",
                tool=ConceptualTool.OPEN_SETTINGS,
                arguments={"panel": "wifi"},
            ),
        ),
        BilingualSemanticFixture(
            fixture_id="semantic_wifi_settings_es",
            pair_id="wifi_settings",
            language="es-MX",
            utterance="abre los ajustes de Wi-Fi",
            expectation=SemanticExpectation(
                intent="open_settings",
                tool=ConceptualTool.OPEN_SETTINGS,
                arguments={"panel": "wifi"},
            ),
        ),
        BilingualSemanticFixture(
            fixture_id="semantic_map_mexico_city_en",
            pair_id="map_mexico_city",
            language="en-US",
            utterance="show Mexico City on the map",
            expectation=SemanticExpectation(
                intent="show_map",
                tool=ConceptualTool.SHOW_MAP,
                arguments={"place": "Mexico City"},
            ),
        ),
        BilingualSemanticFixture(
            fixture_id="semantic_map_mexico_city_es",
            pair_id="map_mexico_city",
            language="es-MX",
            utterance="muestrame Ciudad de Mexico en el mapa",
            expectation=SemanticExpectation(
                intent="show_map",
                tool=ConceptualTool.SHOW_MAP,
                arguments={"place": "Ciudad de Mexico"},
            ),
        ),
        BilingualSemanticFixture(
            fixture_id="semantic_calendar_tomorrow_5pm_en",
            pair_id="calendar_tomorrow_5",
            language="en-US",
            utterance="create a calendar event tomorrow at 5 PM",
            expectation=SemanticExpectation(
                intent="calendar_create_event",
                tool=ConceptualTool.CALENDAR_CREATE_EVENT,
                arguments={"date": "tomorrow", "time": "17:00"},
                relative_datetime="tomorrow 17:00",
            ),
        ),
        BilingualSemanticFixture(
            fixture_id="semantic_calendar_tomorrow_5_es",
            pair_id="calendar_tomorrow_5",
            language="es-MX",
            utterance="crea un evento manana a las 5",
            expectation=SemanticExpectation(
                intent="calendar_create_event",
                tool=ConceptualTool.CALENDAR_CREATE_EVENT,
                arguments={"date": "tomorrow", "time": "ambiguous_5"},
                relative_datetime="tomorrow time_ambiguous",
                clarification_required=True,
            ),
        ),
    )


def evaluate_downstream_semantics(
    provider: ProviderIdentity,
    fixture: BilingualSemanticFixture,
    output: DownstreamSemanticOutput,
) -> DownstreamSemanticEvaluationResult:
    stt_score = _score_text(output.transcript, fixture.utterance)
    intent_score = _score_optional_text(output.intent, fixture.expectation.intent)
    tool_score = 1.0 if output.tool == fixture.expectation.tool else 0.0
    args_score = _score_arguments(output.arguments, fixture.expectation.arguments)
    datetime_score = _score_relative_datetime(
        output.relative_datetime,
        fixture.expectation.relative_datetime,
    )
    clarification_score = _score_clarification(fixture, output)
    e2e_score = _score_end_to_end(
        stt_score,
        intent_score,
        tool_score,
        args_score,
        datetime_score,
        clarification_score,
        fixture.expectation.clarification_required,
    )
    tags = _outcome_tags(
        fixture,
        output,
        stt_score=stt_score,
        tool_score=tool_score,
        datetime_score=datetime_score,
    )
    return DownstreamSemanticEvaluationResult(
        provider=provider,
        fixture_id=fixture.fixture_id,
        pair_id=fixture.pair_id,
        language=fixture.language,
        expected_tool=fixture.expectation.tool,
        observed_tool=output.tool,
        scores=DownstreamSemanticScores(
            stt_transcription_accuracy=stt_score,
            intent_accuracy=intent_score,
            tool_selection_accuracy=tool_score,
            argument_extraction_accuracy=args_score,
            relative_datetime_normalization=datetime_score,
            clarification_quality=clarification_score,
            end_to_end_task_success=e2e_score,
        ),
        outcome_tags=tags,
        simulated_latency_ms=output.simulated_latency_ms,
        failure=output.failure,
    )


def compare_bilingual_pair(
    results: tuple[DownstreamSemanticEvaluationResult, ...],
) -> tuple[SemanticOutcomeTag, ...]:
    by_language = {result.language: result for result in results}
    english = by_language.get("en-US")
    spanish = by_language.get("es-MX")
    if (
        english is not None
        and spanish is not None
        and english.scores.end_to_end_task_success == 1.0
        and spanish.scores.end_to_end_task_success == 0.0
    ):
        return (SemanticOutcomeTag.ENGLISH_PASS_SPANISH_FAIL,)
    return ()


def build_mock_semantic_results(
    provider: ProviderIdentity,
) -> tuple[DownstreamSemanticEvaluationResult, ...]:
    results: list[DownstreamSemanticEvaluationResult] = []
    for fixture in build_bilingual_semantic_fixtures():
        output = DownstreamSemanticOutput(
            transcript=fixture.utterance,
            intent=fixture.expectation.intent,
            tool=fixture.expectation.tool,
            arguments=fixture.expectation.arguments,
            relative_datetime=fixture.expectation.relative_datetime,
            clarification_requested=fixture.expectation.clarification_required,
            clarification_prompt="Should this be AM or PM?"
            if fixture.expectation.clarification_required
            else None,
            simulated_latency_ms=12,
        )
        results.append(evaluate_downstream_semantics(provider, fixture, output))
    return tuple(results)


def _score_text(observed: str, expected: str) -> float:
    return 1.0 if _normalize_text(observed) == _normalize_text(expected) else 0.0


def _score_optional_text(observed: str | None, expected: str) -> float:
    if observed is None:
        return 0.0
    return _score_text(observed, expected)


def _score_arguments(
    observed: Mapping[str, str],
    expected: Mapping[str, str],
) -> float:
    normalized_observed = {
        _normalize_text(key): _normalize_text(value) for key, value in observed.items()
    }
    normalized_expected = {
        _normalize_text(key): _normalize_text(value) for key, value in expected.items()
    }
    return 1.0 if normalized_observed == normalized_expected else 0.0


def _score_relative_datetime(observed: str | None, expected: str | None) -> float:
    if expected is None:
        return 1.0 if observed in (None, "") else 0.0
    if observed is None:
        return 0.0
    return _score_text(observed, expected)


def _score_clarification(
    fixture: BilingualSemanticFixture,
    output: DownstreamSemanticOutput,
) -> float:
    prompt = output.clarification_prompt or ""
    if _is_machine_formatted_clarification(prompt):
        return 0.0
    if fixture.expectation.clarification_required:
        return 1.0 if output.clarification_requested and prompt.strip() else 0.0
    return 1.0 if not output.clarification_requested else 0.0


def _score_end_to_end(
    stt_score: float,
    intent_score: float,
    tool_score: float,
    args_score: float,
    datetime_score: float,
    clarification_score: float,
    clarification_required: bool,
) -> float:
    if clarification_required:
        return 0.0
    scores = (
        stt_score,
        intent_score,
        tool_score,
        args_score,
        datetime_score,
        clarification_score,
    )
    return 1.0 if all(score == 1.0 for score in scores) else 0.0


def _outcome_tags(
    fixture: BilingualSemanticFixture,
    output: DownstreamSemanticOutput,
    *,
    stt_score: float,
    tool_score: float,
    datetime_score: float,
) -> tuple[SemanticOutcomeTag, ...]:
    tags: list[SemanticOutcomeTag] = []
    if fixture.language == "es-MX" and stt_score == 1.0 and tool_score == 0.0:
        tags.append(SemanticOutcomeTag.SPANISH_TRANSCRIPT_PASS_TOOL_FAIL)
    if fixture.expectation.relative_datetime is not None and datetime_score == 0.0:
        tags.append(SemanticOutcomeTag.RELATIVE_DATETIME_NOT_NORMALIZED)
    if _is_machine_formatted_clarification(output.clarification_prompt or ""):
        tags.append(SemanticOutcomeTag.MACHINE_FORMATTED_CLARIFICATION_REQUESTED)
    if fixture.expectation.clarification_required:
        tags.append(SemanticOutcomeTag.CLARIFICATION_NEEDED)
    elif output.clarification_requested:
        tags.append(SemanticOutcomeTag.CLARIFICATION_UNNECESSARY)
    return tuple(tags)


def _is_machine_formatted_clarification(prompt: str) -> bool:
    normalized = prompt.lower()
    return bool(
        re.search(r"\b\d{4}-\d{2}-\d{2}\b", normalized)
        or re.search(r"\biso\b", normalized)
        or re.search(r"\bapi\b", normalized)
        or re.search(r"\btimestamp\b", normalized)
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.lower().replace("-", " ").split())
