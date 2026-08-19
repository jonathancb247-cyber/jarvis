"""Provider-neutral contracts for future STT/TTS bake-off evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Protocol


class ProviderDeployment(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"


class ProviderFailureCategory(str, Enum):
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    INVALID_INPUT = "invalid_input"
    QUOTA_OR_CAPACITY = "quota_or_capacity"
    MALFORMED_OUTPUT = "malformed_output"
    PROVIDER_ERROR = "provider_error"


class FixtureCategory(str, Enum):
    MEXICAN_SPANISH = "mexican_spanish"
    NEUTRAL_SPANISH = "neutral_spanish"
    CODE_SWITCHING = "code_switching"
    SHORT_COMMAND = "short_command"
    NATURAL_PHRASING = "natural_phrasing"
    TECHNICAL_VOCABULARY = "technical_vocabulary"
    DEVICE_NAMES = "device_names"
    ACRONYMS = "acronyms"
    HESITATION = "hesitation"
    SELF_CORRECTION = "self_correction"
    AMBIGUITY = "ambiguity"
    ACKNOWLEDGEMENT = "acknowledgement"
    CONFIRMATION = "confirmation"
    REFUSAL = "refusal"
    WARNING = "warning"
    LONG_EXPLANATION = "long_explanation"
    HUMAN_FACING_DEVICE_NAMES = "human_facing_device_names"
    NUMBERS_DATES = "numbers_dates"
    BILINGUAL_TERMS = "bilingual_terms"
    URGENT_CALM_RESPONSE = "urgent_calm_response"
    REPEATED_LONG_SESSION_PHRASE = "repeated_long_session_phrase"


@dataclass(frozen=True)
class ProviderIdentity:
    name: str
    mode: str
    deployment: ProviderDeployment
    version_or_model: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("provider name is required")
        if not self.mode.strip():
            raise ValueError("provider mode is required")


@dataclass(frozen=True)
class STTCapabilities:
    batch: bool = True
    streaming: bool = False
    partial_results: bool = False
    language_detection: bool = False
    timestamps: bool = False
    confidence: bool = False
    vocabulary_hints: bool = False
    cancellation: bool = False
    local_offline: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "batch": self.batch,
            "streaming": self.streaming,
            "partial_results": self.partial_results,
            "language_detection": self.language_detection,
            "timestamps": self.timestamps,
            "confidence": self.confidence,
            "vocabulary_hints": self.vocabulary_hints,
            "cancellation": self.cancellation,
            "local_offline": self.local_offline,
        }


@dataclass(frozen=True)
class TTSCapabilities:
    batch: bool = True
    streaming: bool = False
    interruption: bool = False
    styles: bool = False
    prosody_controls: bool = False
    ssml_or_equivalent: bool = False
    local_offline: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "batch": self.batch,
            "streaming": self.streaming,
            "interruption": self.interruption,
            "styles": self.styles,
            "prosody_controls": self.prosody_controls,
            "ssml_or_equivalent": self.ssml_or_equivalent,
            "local_offline": self.local_offline,
        }


@dataclass(frozen=True)
class STTFixture:
    fixture_id: str
    categories: tuple[FixtureCategory, ...]
    expected_transcript: str
    language_hint: str = "es-MX"
    audio_reference: str | None = None
    private_user_audio: bool = False

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if not self.categories:
            raise ValueError("at least one fixture category is required")
        if self.private_user_audio:
            raise ValueError("private user audio is not allowed in Phase 2A")


@dataclass(frozen=True)
class TTSPhraseFixture:
    fixture_id: str
    categories: tuple[FixtureCategory, ...]
    text: str
    language: str = "es-MX"

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if not self.text.strip():
            raise ValueError("text is required")
        if not self.categories:
            raise ValueError("at least one fixture category is required")


@dataclass(frozen=True)
class PartialTranscriptEvent:
    transcript: str
    simulated_latency_ms: int | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.transcript.strip():
            raise ValueError("partial transcript is required")
        _validate_optional_non_negative(self.simulated_latency_ms, "simulated_latency_ms")
        _validate_optional_confidence(self.confidence)


@dataclass(frozen=True)
class ProviderFailure:
    category: ProviderFailureCategory
    safe_message: str

    def __post_init__(self) -> None:
        if not self.safe_message.strip():
            raise ValueError("safe_message is required")
        if "\n" in self.safe_message or "\r" in self.safe_message:
            raise ValueError("safe_message must be single-line")


@dataclass(frozen=True)
class STTEvaluationResult:
    provider: ProviderIdentity
    fixture_id: str
    capabilities: STTCapabilities
    final_transcript: str | None = None
    partials: tuple[PartialTranscriptEvent, ...] = ()
    detected_language: str | None = None
    confidence: float | None = None
    transcript_latency_ms: int | None = None
    partial_latency_ms: int | None = None
    failure: ProviderFailure | None = None
    metrics: Mapping[str, float | int | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        _validate_optional_confidence(self.confidence)
        _validate_optional_non_negative(self.transcript_latency_ms, "transcript_latency_ms")
        _validate_optional_non_negative(self.partial_latency_ms, "partial_latency_ms")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        if self.failure is None and not self.final_transcript:
            raise ValueError("successful STT result requires final_transcript")


@dataclass(frozen=True)
class TTSEvaluationResult:
    provider: ProviderIdentity
    fixture_id: str
    capabilities: TTSCapabilities
    synthesized_output_reference: str | None = None
    first_audio_ms: int | None = None
    total_synthesis_ms: int | None = None
    failure: ProviderFailure | None = None
    metrics: Mapping[str, float | int | str] = field(default_factory=dict)
    human_rating: "HumanRating | None" = None

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        _validate_optional_non_negative(self.first_audio_ms, "first_audio_ms")
        _validate_optional_non_negative(self.total_synthesis_ms, "total_synthesis_ms")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))
        if self.failure is None and not self.synthesized_output_reference:
            raise ValueError("successful TTS result requires synthesized_output_reference")


@dataclass(frozen=True)
class HumanRating:
    naturalness: int | None = None
    fatigue_annoyance: int | None = None
    pronunciation_notes: str = ""
    pacing_prosody_notes: str = ""
    preference_ranking_notes: str = ""

    def __post_init__(self) -> None:
        _validate_optional_rating(self.naturalness, "naturalness")
        _validate_optional_rating(self.fatigue_annoyance, "fatigue_annoyance")


class STTEvaluationProvider(Protocol):
    identity: ProviderIdentity
    capabilities: STTCapabilities

    def evaluate_stt(self, fixture: STTFixture) -> STTEvaluationResult:
        ...


class TTSEvaluationProvider(Protocol):
    identity: ProviderIdentity
    capabilities: TTSCapabilities

    def evaluate_tts(self, fixture: TTSPhraseFixture) -> TTSEvaluationResult:
        ...


def normalize_provider_exception(error: Exception) -> ProviderFailure:
    del error
    return ProviderFailure(
        ProviderFailureCategory.PROVIDER_ERROR,
        "provider_error",
    )


def _validate_optional_rating(value: int | None, name: str) -> None:
    if value is not None and not 1 <= value <= 5:
        raise ValueError(f"{name} must be between 1 and 5")


def _validate_optional_confidence(value: float | None) -> None:
    if value is not None and not 0 <= value <= 1:
        raise ValueError("confidence must be between 0 and 1")


def _validate_optional_non_negative(value: int | None, name: str) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be non-negative")
