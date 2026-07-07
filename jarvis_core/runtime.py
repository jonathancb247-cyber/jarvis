"""Runtime bootstrap helpers for JarvisOS AVP-001."""

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.domain import CapabilityResult, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry


class Runtime:
    """Coordinates planning and command execution for the AVP-001 runtime."""

    def __init__(self, planner, context):
        self.planner = planner
        self.context = context

    def handle_user_input(self, text):
        command = self.planner.plan(text)
        result = self.execute(command)
        return result.message

    def execute(self, command):
        if command.name == "unknown":
            return CapabilityResult(
                success=False,
                message="I do not know how to handle that yet.",
                data={"command": command.name, "args": command.args},
                error="unknown_command",
            )

        try:
            capability = self.context.capability_registry.resolve(command.name)
        except KeyError:
            return CapabilityResult(
                success=False,
                message="I do not know how to handle that yet.",
                data={"command": command.name, "args": command.args},
                error="capability_not_found",
            )
        return capability.run(command, self.context)


def build_runtime():
    """Build the minimal AVP-001 runtime and return its event bus."""
    bus = EventBus()
    registry = CapabilityRegistry()
    registry.register(ClockCapability.name, ClockCapability())
    planner = Planner()
    context = RuntimeContext(event_bus=bus, capability_registry=registry)
    runtime = Runtime(planner, context)

    def route_user_input(payload):
        return runtime.handle_user_input(payload.get("text", ""))

    bus.subscribe("user.input", route_user_input)
    return bus
