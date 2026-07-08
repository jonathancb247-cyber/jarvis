"""Core domain objects for JarvisOS AVP-001."""

from dataclasses import dataclass, field


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
class RuntimeContext:
    """Runtime resources available while executing commands."""

    event_bus: object
    capability_registry: object
    device_registry: object = None
