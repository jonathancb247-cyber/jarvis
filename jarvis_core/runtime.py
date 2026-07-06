"""Runtime bootstrap helpers for JarvisOS AVP-001."""

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry


def build_runtime():
    """Build the minimal AVP-001 runtime and return its event bus."""
    bus = EventBus()
    registry = CapabilityRegistry()
    registry.register(ClockCapability.name, ClockCapability())
    planner = Planner(registry)

    def route_user_input(payload):
        return planner.execute(payload.get("text", ""))

    bus.subscribe("user.input", route_user_input)
    return bus
