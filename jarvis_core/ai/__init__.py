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
from jarvis_core.ai.groq import (
    DEFAULT_GROQ_MODEL,
    GroqAIProvider,
    GroqProviderConfig,
    groq_ai_action_plan_schema,
)
from jarvis_core.ai.provider import AIProvider, AIProviderError

__all__ = [
    "AIActionPlan",
    "AIActionStep",
    "AIAdapterResult",
    "AIClarification",
    "AIConfirmationState",
    "AIPlanExecutionSummary",
    "AIRefusal",
    "AISafeCapability",
    "AISafeContext",
    "AISafeDevice",
    "AISafeDeviceState",
    "AISafePolicyContext",
    "AISafeResult",
    "AIProvider",
    "AIProviderError",
    "DEFAULT_GROQ_MODEL",
    "DeterministicFakeAIProvider",
    "FakeAIAdapter",
    "GroqAIProvider",
    "GroqProviderConfig",
    "groq_ai_action_plan_schema",
]
