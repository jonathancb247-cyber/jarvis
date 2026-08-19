"""Comparable provider bake-off reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .provider_contracts import (
    ProviderFailureCategory,
    ProviderIdentity,
    STTEvaluationResult,
    TTSEvaluationResult,
)


class ProviderRecommendation(str, Enum):
    CONTINUE = "continue"
    PROMISING = "promising"
    POOR_FIT = "poor_fit"
    DEFER = "defer"


@dataclass(frozen=True)
class ProviderBakeOffReport:
    provider: ProviderIdentity
    fixture_set: str
    stt_results: tuple[STTEvaluationResult, ...] = ()
    tts_results: tuple[TTSEvaluationResult, ...] = ()
    privacy_notes: tuple[str, ...] = ()
    cost_quota_notes: tuple[str, ...] = ()
    known_limitations: tuple[str, ...] = ()
    recommendation: ProviderRecommendation = ProviderRecommendation.DEFER
    synthetic_only: bool = True
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fixture_set.strip():
            raise ValueError("fixture_set is required")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def normalized_failures(self) -> tuple[ProviderFailureCategory, ...]:
        failures: list[ProviderFailureCategory] = []
        for result in self.stt_results:
            if result.failure is not None:
                failures.append(result.failure.category)
        for result in self.tts_results:
            if result.failure is not None:
                failures.append(result.failure.category)
        return tuple(failures)

    def capability_summary(self) -> dict[str, object]:
        stt = self.stt_results[0].capabilities.as_dict() if self.stt_results else None
        tts = self.tts_results[0].capabilities.as_dict() if self.tts_results else None
        return {
            "stt": stt,
            "tts": tts,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_name": self.provider.name,
            "provider_mode": self.provider.mode,
            "version_or_model": self.provider.version_or_model,
            "local_or_cloud": self.provider.deployment.value,
            "capability_summary": self.capability_summary(),
            "fixture_set": self.fixture_set,
            "stt_metrics": [_stt_result_dict(result) for result in self.stt_results],
            "tts_metrics": [_tts_result_dict(result) for result in self.tts_results],
            "normalized_failures": [failure.value for failure in self.normalized_failures()],
            "privacy_notes": list(self.privacy_notes),
            "cost_quota_notes": list(self.cost_quota_notes),
            "human_rating_summary": [_human_rating_dict(result) for result in self.tts_results],
            "known_limitations": list(self.known_limitations),
            "recommendation": self.recommendation.value,
            "synthetic_only": self.synthetic_only,
            "metadata": dict(self.metadata),
        }


def validate_no_secret_markers(report: ProviderBakeOffReport) -> tuple[str, ...]:
    forbidden = ("api_key", "authorization", "bearer ", "secret", "token", "password")
    haystack = repr(report.as_dict()).lower()
    return tuple(marker for marker in forbidden if marker in haystack)


def _stt_result_dict(result: STTEvaluationResult) -> dict[str, object]:
    return {
        "fixture_id": result.fixture_id,
        "final_transcript_present": result.final_transcript is not None,
        "partial_count": len(result.partials),
        "detected_language": result.detected_language,
        "confidence": result.confidence,
        "transcript_latency_ms": result.transcript_latency_ms,
        "partial_latency_ms": result.partial_latency_ms,
        "failure": result.failure.category.value if result.failure else None,
        "metrics": dict(result.metrics),
        "synthetic_test_values": True,
    }


def _tts_result_dict(result: TTSEvaluationResult) -> dict[str, object]:
    return {
        "fixture_id": result.fixture_id,
        "synthesized_output_reference_present": result.synthesized_output_reference is not None,
        "first_audio_ms": result.first_audio_ms,
        "total_synthesis_ms": result.total_synthesis_ms,
        "failure": result.failure.category.value if result.failure else None,
        "metrics": dict(result.metrics),
        "synthetic_test_values": True,
    }


def _human_rating_dict(result: TTSEvaluationResult) -> dict[str, object]:
    rating = result.human_rating
    if rating is None:
        return {
            "fixture_id": result.fixture_id,
            "naturalness": None,
            "fatigue_annoyance": None,
            "notes": "not_evaluated",
        }
    return {
        "fixture_id": result.fixture_id,
        "naturalness": rating.naturalness,
        "fatigue_annoyance": rating.fatigue_annoyance,
        "pronunciation_notes": rating.pronunciation_notes,
        "pacing_prosody_notes": rating.pacing_prosody_notes,
        "preference_ranking_notes": rating.preference_ranking_notes,
    }
