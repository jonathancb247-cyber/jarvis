"""Internal provider protocol for the experimental AI Adapter boundary."""

from typing import Protocol

from jarvis_core.ai.contracts import AISafeContext


class AIProvider(Protocol):
    """Provider boundary that returns raw Structured Plan payloads."""

    def generate_plan(self, context: AISafeContext) -> object:
        """Return a provider-neutral raw plan payload for adapter normalization."""

