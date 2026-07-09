"""Runtime boundary and bootstrap helpers for JarvisOS AVP-001.

The runtime coordinates command execution. It does not define domain
entities, parse user intent, manage physical devices, or talk to external
systems directly.
"""

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.devices import DeviceRegistry
from jarvis_core.domain import CapabilityResult, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry


UNKNOWN_COMMAND_ERROR = "unknown_command"
CAPABILITY_NOT_FOUND_ERROR = "capability_not_found"
CAPABILITY_EXECUTION_ERROR = "capability_execution_failed"
INVALID_CAPABILITY_RESULT_ERROR = "invalid_capability_result"
UNKNOWN_COMMAND_MESSAGE = "I do not know how to handle that yet."
RUNTIME_ERROR_MESSAGE = "I could not complete that command."


class Runtime:
    """Coordinates planning and command execution across runtime boundaries.

    Planner turns input into a Command. Runtime resolves and executes the
    command through registered capabilities. Capabilities return
    CapabilityResult. Adapters decide how to present the result.
    """

    def __init__(self, planner, context):
        self.planner = planner
        self.context = context

    def handle_user_input(self, text):
        """Plan text input and return the user-facing message.

        This preserves the AVP-001 CLI contract: adapters receive a printable
        message, while Runtime.execute keeps the structured result boundary.
        """
        command = self.planner.plan(text)
        result = self.execute(command)
        return result.message

    def execute(self, command):
        """Execute a Command and always return a CapabilityResult."""
        if command.name == "unknown":
            return self._failure(command, UNKNOWN_COMMAND_ERROR, UNKNOWN_COMMAND_MESSAGE)

        try:
            capability = self.context.capability_registry.resolve(command.name)
        except KeyError:
            return self._failure(
                command,
                CAPABILITY_NOT_FOUND_ERROR,
                UNKNOWN_COMMAND_MESSAGE,
            )

        try:
            result = capability.run(command, self.context)
        except Exception as error:
            return self._failure(
                command,
                CAPABILITY_EXECUTION_ERROR,
                RUNTIME_ERROR_MESSAGE,
                details=str(error),
            )
        if not isinstance(result, CapabilityResult):
            return self._failure(
                command,
                INVALID_CAPABILITY_RESULT_ERROR,
                RUNTIME_ERROR_MESSAGE,
                details="Capability returned an invalid result",
            )
        return result

    def _failure(self, command, error, message, details=None):
        data = {
            "command": command.name,
            "args": command.args,
            "source": command.source,
        }
        if details:
            data["details"] = details
        return CapabilityResult(
            success=False,
            message=message,
            data=data,
            error=error,
        )


def build_runtime():
    """Wire the minimal AVP-001 core and return its adapter-facing bus."""
    bus = EventBus()
    registry = CapabilityRegistry()
    device_registry = DeviceRegistry()
    registry.register(ClockCapability.name, ClockCapability())
    planner = Planner()
    context = RuntimeContext(
        event_bus=bus,
        capability_registry=registry,
        device_registry=device_registry,
    )
    runtime = Runtime(planner, context)

    def route_user_input(payload):
        return runtime.handle_user_input(payload.get("text", ""))

    bus.subscribe("user.input", route_user_input)
    return bus
