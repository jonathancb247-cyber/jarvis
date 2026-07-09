"""Core domain objects for JarvisOS AVP-001."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Command:
    """An executable action understood by the JarvisOS runtime."""

    name: str
    args: dict = field(default_factory=dict)
    source: str = "cli"


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
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeContext:
    """Runtime resources available while executing commands."""

    event_bus: object
    capability_registry: object
    device_registry: object = None
