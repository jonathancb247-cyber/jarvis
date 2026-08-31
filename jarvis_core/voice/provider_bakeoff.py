"""Offline-safe provider bake-off foundation using mock providers only."""

from __future__ import annotations

from dataclasses import dataclass

from .provider_contracts import (
    FixtureCategory,
    HumanRating,
    PartialTranscriptEvent,
    ProviderDeployment,
    ProviderFailure,
    ProviderFailureCategory,
    ProviderIdentity,
    STTCapabilities,
    STTEvaluationResult,
    STTFixture,
    TTSCapabilities,
    TTSEvaluationResult,
    TTSPhraseFixture,
)
from .provider_reports import ProviderBakeOffReport, ProviderRecommendation
from .semantic_bakeoff import (
    build_bilingual_semantic_fixtures,
    build_mock_semantic_results,
)


def build_default_stt_fixtures() -> tuple[STTFixture, ...]:
    return (
        STTFixture(
            "stt_mexican_spanish_short_command",
            (
                FixtureCategory.MEXICAN_SPANISH,
                FixtureCategory.SHORT_COMMAND,
                FixtureCategory.DEVICE_NAMES,
            ),
            "enciende la lampara",
        ),
        STTFixture(
            "stt_code_switching_technical",
            (
                FixtureCategory.CODE_SWITCHING,
                FixtureCategory.TECHNICAL_VOCABULARY,
                FixtureCategory.ACRONYMS,
            ),
            "revisa el ESP32 y el estado MQTT",
        ),
        STTFixture(
            "stt_self_correction",
            (
                FixtureCategory.NATURAL_PHRASING,
                FixtureCategory.HESITATION,
                FixtureCategory.SELF_CORRECTION,
            ),
            "apaga la luz no espera enciende la del pasillo",
        ),
        STTFixture(
            "stt_ambiguous_obd",
            (
                FixtureCategory.AMBIGUITY,
                FixtureCategory.TECHNICAL_VOCABULARY,
                FixtureCategory.ACRONYMS,
            ),
            "y de OBD-II que dice",
        ),
    )


def build_default_tts_fixtures() -> tuple[TTSPhraseFixture, ...]:
    return (
        TTSPhraseFixture(
            "tts_acknowledgement",
            (FixtureCategory.ACKNOWLEDGEMENT,),
            "Listo.",
        ),
        TTSPhraseFixture(
            "tts_confirmation",
            (FixtureCategory.CONFIRMATION, FixtureCategory.HUMAN_FACING_DEVICE_NAMES),
            "Voy a encender la lampara. Confirmas?",
        ),
        TTSPhraseFixture(
            "tts_warning",
            (FixtureCategory.WARNING, FixtureCategory.URGENT_CALM_RESPONSE),
            "No puedo hacer eso de forma segura.",
        ),
        TTSPhraseFixture(
            "tts_refusal",
            (FixtureCategory.REFUSAL,),
            "No puedo realizar esa solicitud.",
        ),
        TTSPhraseFixture(
            "tts_technical_terms",
            (
                FixtureCategory.BILINGUAL_TERMS,
                FixtureCategory.TECHNICAL_VOCABULARY,
                FixtureCategory.NUMBERS_DATES,
            ),
            "El ESP32 respondio, pero MQTT y OBD-II siguen pendientes.",
        ),
        TTSPhraseFixture(
            "tts_long_session",
            (
                FixtureCategory.LONG_EXPLANATION,
                FixtureCategory.REPEATED_LONG_SESSION_PHRASE,
            ),
            "Puedo resumirlo en corto y dejar los detalles para despues.",
        ),
    )


@dataclass(frozen=True)
class MockSTTProvider:
    identity: ProviderIdentity
    capabilities: STTCapabilities
    failure: ProviderFailure | None = None
    malformed: bool = False

    def evaluate_stt(self, fixture: STTFixture) -> STTEvaluationResult:
        if self.failure is not None:
            return STTEvaluationResult(
                self.identity,
                fixture.fixture_id,
                self.capabilities,
                failure=self.failure,
            )
        if self.malformed:
            return STTEvaluationResult(
                self.identity,
                fixture.fixture_id,
                self.capabilities,
                failure=ProviderFailure(
                    ProviderFailureCategory.MALFORMED_OUTPUT,
                    "malformed_output",
                ),
            )
        return STTEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            final_transcript=fixture.expected_transcript,
            partials=(
                PartialTranscriptEvent(
                    fixture.expected_transcript.split(" ", 1)[0],
                    simulated_latency_ms=25,
                    confidence=0.5,
                ),
            )
            if self.capabilities.partial_results
            else (),
            detected_language=fixture.language_hint
            if self.capabilities.language_detection
            else None,
            confidence=0.91 if self.capabilities.confidence else None,
            transcript_latency_ms=80,
            partial_latency_ms=25 if self.capabilities.partial_results else None,
            metrics={
                "wer": 0,
                "downstream_intent_accuracy": 1,
                "technical_term_accuracy": 1,
                "synthetic_test_values": 1,
            },
        )


@dataclass(frozen=True)
class MockTTSProvider:
    identity: ProviderIdentity
    capabilities: TTSCapabilities
    failure: ProviderFailure | None = None
    malformed: bool = False

    def evaluate_tts(self, fixture: TTSPhraseFixture) -> TTSEvaluationResult:
        if self.failure is not None:
            return TTSEvaluationResult(
                self.identity,
                fixture.fixture_id,
                self.capabilities,
                failure=self.failure,
            )
        if self.malformed:
            return TTSEvaluationResult(
                self.identity,
                fixture.fixture_id,
                self.capabilities,
                failure=ProviderFailure(
                    ProviderFailureCategory.MALFORMED_OUTPUT,
                    "malformed_output",
                ),
            )
        return TTSEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            synthesized_output_reference=f"synthetic://{fixture.fixture_id}",
            first_audio_ms=30,
            total_synthesis_ms=95,
            metrics={
                "time_to_first_audio_ms": 30,
                "total_synthesis_time_ms": 95,
                "synthetic_test_values": 1,
            },
            human_rating=HumanRating(),
        )


def build_mock_provider_identity(name: str = "mock-provider") -> ProviderIdentity:
    return ProviderIdentity(
        name=name,
        mode="mock",
        deployment=ProviderDeployment.LOCAL,
        version_or_model="phase-2a-mock",
    )


def build_mock_bakeoff_report(
    *,
    stt_failure: ProviderFailure | None = None,
    tts_failure: ProviderFailure | None = None,
) -> ProviderBakeOffReport:
    identity = build_mock_provider_identity()
    stt_provider = MockSTTProvider(
        identity,
        STTCapabilities(
            partial_results=True,
            language_detection=True,
            timestamps=True,
            confidence=True,
            vocabulary_hints=True,
            cancellation=True,
            local_offline=True,
        ),
        failure=stt_failure,
    )
    tts_provider = MockTTSProvider(
        identity,
        TTSCapabilities(
            interruption=True,
            styles=True,
            prosody_controls=True,
            local_offline=True,
        ),
        failure=tts_failure,
    )
    return ProviderBakeOffReport(
        provider=identity,
        fixture_set="phase-2a-synthetic-fixtures",
        stt_results=tuple(
            stt_provider.evaluate_stt(fixture)
            for fixture in build_default_stt_fixtures()
        ),
        tts_results=tuple(
            tts_provider.evaluate_tts(fixture)
            for fixture in build_default_tts_fixtures()
        ),
        semantic_results=build_mock_semantic_results(identity),
        privacy_notes=("synthetic fixtures only", "no credentials", "no network"),
        cost_quota_notes=("not evaluated in Phase 2A",),
        known_limitations=("no real provider evaluated", "no real audio measured"),
        recommendation=ProviderRecommendation.CONTINUE,
        synthetic_only=True,
    )


__all__ = [
    "MockSTTProvider",
    "MockTTSProvider",
    "build_bilingual_semantic_fixtures",
    "build_default_stt_fixtures",
    "build_default_tts_fixtures",
    "build_mock_bakeoff_report",
    "build_mock_provider_identity",
]
