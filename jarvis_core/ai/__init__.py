"""Experimental AI Adapter boundary for JarvisOS.

This package is intentionally not wired into the default runtime.
"""

from jarvis_core.ai.adapter import FakeAIAdapter
from jarvis_core.ai.contracts import (
    AIActionPlan,
    AIActionStep,
    AIAdapterResult,
    AIClarification,
    AIConfirmationState,
    AIPlanExecutionSummary,
    AIRefusal,
    AISafeCapability,
    AISafeContext,
    AISafeDevice,
    AISafeDeviceState,
    AISafePolicyContext,
    AISafeResult,
)
from jarvis_core.ai.fake_provider import DeterministicFakeAIProvider
from jarvis_core.ai.gemini import GeminiAIProvider, GeminiProviderConfig
from jarvis_core.ai.ollama import OllamaAIProvider, OllamaProviderConfig
from jarvis_core.ai.provider import AIProvider

__all__ = [
    "AIActionPlan",
    "AIActionStep",
    "AIAdapterResult",
    "AIClarification",
    "AIConfirmationState",
    "AIPlanExecutionSummary",
    "AIProvider",
    "AIRefusal",
    "AISafeCapability",
    "AISafeContext",
    "AISafeDevice",
    "AISafeDeviceState",
    "AISafePolicyContext",
    "AISafeResult",
    "DeterministicFakeAIProvider",
    "FakeAIAdapter",
    "GeminiAIProvider",
    "GeminiProviderConfig",
    "OllamaAIProvider",
    "OllamaProviderConfig",
]
