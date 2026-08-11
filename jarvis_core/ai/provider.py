"""Internal AI provider protocol for optional adapter-layer providers."""

from typing import Protocol

from jarvis_core.ai.contracts import AISafeContext


class AIProvider(Protocol):
    """Generate one raw provider response from a detached safe context."""

    def generate_plan(self, context: AISafeContext) -> object:
        ...
