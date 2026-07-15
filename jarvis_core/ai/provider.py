"""Internal AI provider boundary for adapter-layer providers."""

from typing import Protocol


class AIProvider(Protocol):
    """Minimal provider interface used by the AI Adapter package."""

    def generate_plan(self, context):
        """Return raw provider data for existing AIActionPlan normalization."""


class AIProviderError(Exception):
    """Safe provider error carrying only a normalized adapter error code."""

    def __init__(self, code):
        super().__init__("AI provider request failed")
        self.code = code
