"""Core domain objects for JarvisOS AVP-001."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Command:
    """An executable action understood by the JarvisOS runtime."""

    name: str
    args: dict = field(default_factory=dict)
    source: str = "cli"

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Command name must be a non-empty string")
        if not isinstance(self.args, dict):
            raise ValueError("Command args must be a dict")
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("Command source must be a non-empty string")


@dataclass
class CapabilityResult:
    """Structured result returned by a capability execution."""

    success: bool
    message: str
    data: dict = field(default_factory=dict)
    error: str = None


@dataclass
class Event:
    """Internal domain signal describing something that happened."""

    type: str
    source: str
    payload: dict = field(default_factory=dict)
    timestamp: str = None
    correlation_id: str = None
    causation_id: str = None

    def __post_init__(self):
        if not isinstance(self.type, str) or not self.type:
            raise ValueError("Event type must be a non-empty string")
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("Event source must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise ValueError("Event payload must be a dict")
        if self.correlation_id is not None and (
            not isinstance(self.correlation_id, str) or not self.correlation_id
        ):
            raise ValueError("Event correlation_id must be None or a non-empty string")
        if self.causation_id is not None and (
            not isinstance(self.causation_id, str) or not self.causation_id
        ):
            raise ValueError("Event causation_id must be None or a non-empty string")
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeContext:
    """Runtime resources available while executing commands."""

    event_bus: object
    capability_registry: object
    device_registry: object = None

    def __post_init__(self):
        if self.event_bus is None:
            raise ValueError("RuntimeContext event_bus is required")
        if self.capability_registry is None:
            raise ValueError("RuntimeContext capability_registry is required")
