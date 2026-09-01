"""Opt-in real voice provider adapters for benchmark evaluation only."""

from .groq_stt import (
    GROQ_STT_MODELS,
    GroqSTTConfig,
    GroqSTTProvider,
    GroqSTTResponse,
    GroqSTTTransport,
    StdlibGroqSTTTransport,
)
from .piper_tts import (
    PiperTTSConfig,
    PiperTTSProvider,
    PiperTTSRunner,
    PiperTTSRunResult,
)
from .whisper_cpp_stt import (
    WhisperCppSTTConfig,
    WhisperCppSTTProvider,
    WhisperCppSTTRunResult,
    WhisperCppSTTRunner,
)

__all__ = [
    "GROQ_STT_MODELS",
    "GroqSTTConfig",
    "GroqSTTProvider",
    "GroqSTTResponse",
    "GroqSTTTransport",
    "PiperTTSConfig",
    "PiperTTSProvider",
    "PiperTTSRunner",
    "PiperTTSRunResult",
    "StdlibGroqSTTTransport",
    "WhisperCppSTTConfig",
    "WhisperCppSTTProvider",
    "WhisperCppSTTRunResult",
    "WhisperCppSTTRunner",
]
