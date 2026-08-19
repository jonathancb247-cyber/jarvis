"""Deterministic fake voice benchmark helpers for JarvisOS."""

from .benchmark import (
    BenchmarkReport,
    BenchmarkScenarioResult,
    VoiceBenchmarkRunner,
    build_phase1_scenarios,
)
from .events import VoiceEvent, VoiceEventKind
from .fakes import FakeSTTProvider, FakeTTSProvider
from .provider_bakeoff import (
    build_default_stt_fixtures,
    build_default_tts_fixtures,
    build_mock_bakeoff_report,
)
from .provider_contracts import (
    ProviderFailureCategory,
    STTCapabilities,
    STTEvaluationResult,
    STTFixture,
    TTSCapabilities,
    TTSEvaluationResult,
    TTSPhraseFixture,
)
from .provider_reports import ProviderBakeOffReport, ProviderRecommendation
from .session import ConversationSession
from .turns import TurnManager

__all__ = [
    "BenchmarkReport",
    "BenchmarkScenarioResult",
    "ConversationSession",
    "FakeSTTProvider",
    "FakeTTSProvider",
    "ProviderBakeOffReport",
    "ProviderFailureCategory",
    "ProviderRecommendation",
    "STTCapabilities",
    "STTEvaluationResult",
    "STTFixture",
    "TTSCapabilities",
    "TTSEvaluationResult",
    "TTSPhraseFixture",
    "TurnManager",
    "VoiceBenchmarkRunner",
    "VoiceEvent",
    "VoiceEventKind",
    "build_default_stt_fixtures",
    "build_default_tts_fixtures",
    "build_mock_bakeoff_report",
    "build_phase1_scenarios",
]
