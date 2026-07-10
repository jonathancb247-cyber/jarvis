"""Runtime boundary and bootstrap helpers for JarvisOS AVP-001.

The runtime coordinates command execution. It does not define domain
entities, parse user intent, manage physical devices, or talk to external
systems directly.
"""

import logging
from uuid import uuid4

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.devices import DeviceRegistry
from jarvis_core.domain import CapabilityResult, Event, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry


UNKNOWN_COMMAND_ERROR = "unknown_command"
CAPABILITY_NOT_FOUND_ERROR = "capability_not_found"
CAPABILITY_EXECUTION_ERROR = "capability_execution_failed"
INVALID_CAPABILITY_RESULT_ERROR = "invalid_capability_result"
INVALID_ADAPTER_INPUT_ERROR = "invalid_adapter_input"
UNKNOWN_COMMAND_MESSAGE = "I do not know how to handle that yet."
RUNTIME_ERROR_MESSAGE = "I could not complete that command."
ADAPTER_INPUT_ERROR_MESSAGE = "I could not process that input."
USER_INPUT_RECEIVED_EVENT = "user.input.received"
COMMAND_PLANNED_EVENT = "command.planned"
COMMAND_EXECUTION_STARTED_EVENT = "command.execution.started"
CAPABILITY_EXECUTION_COMPLETED_EVENT = "capability.execution.completed"
CAPABILITY_EXECUTION_FAILED_EVENT = "capability.execution.failed"
RUNTIME_ERROR_EVENT = "runtime.error"

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


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
        return self.handle_adapter_input(text).message

    def handle_adapter_input(self, text, source="cli"):
        """Runtime-owned boundary for external adapter input.

        Adapters enter JarvisOS here. Runtime owns the internal Event creation,
        planning, and command execution flow. EventBus remains an internal
        transport and is not exposed as an adapter-facing API.
        """
        correlation_id = self._new_correlation_id()
        if not isinstance(source, str) or not source.strip():
            self._record_runtime_error(
                INVALID_ADAPTER_INPUT_ERROR,
                "invalid adapter source",
                correlation_id,
                source=source,
            )
            return self._adapter_input_failure(source)
        if not isinstance(text, str) or not text.strip():
            self._record_runtime_error(
                INVALID_ADAPTER_INPUT_ERROR,
                "invalid adapter text input",
                correlation_id,
                source=source,
            )
            return self._adapter_input_failure(source)

        self._publish_event(
            type=USER_INPUT_RECEIVED_EVENT,
            source=source,
            payload={"input_length": len(text)},
            correlation_id=correlation_id,
        )
        logger.info(
            "adapter input received",
            extra={
                "correlation_id": correlation_id,
                "source": source,
                "input_length": len(text),
            },
        )

        command = self.planner.plan(text)
        self._publish_event(
            type=COMMAND_PLANNED_EVENT,
            source="runtime",
            payload={
                "command": command.name,
                "command_source": command.source,
            },
            correlation_id=correlation_id,
        )
        logger.info(
            "command planned",
            extra={
                "correlation_id": correlation_id,
                "command": command.name,
                "command_source": command.source,
            },
        )
        return self.execute(command, correlation_id=correlation_id)

    def execute(self, command, correlation_id=None):
        """Execute a Command and always return a CapabilityResult."""
        self._publish_event(
            type=COMMAND_EXECUTION_STARTED_EVENT,
            source="runtime",
            payload={
                "command": command.name,
                "command_source": command.source,
            },
            correlation_id=correlation_id,
        )
        logger.info(
            "command execution started",
            extra={
                "correlation_id": correlation_id,
                "command": command.name,
                "command_source": command.source,
            },
        )

        if command.name == "unknown":
            return self._failure(
                command,
                UNKNOWN_COMMAND_ERROR,
                UNKNOWN_COMMAND_MESSAGE,
                correlation_id=correlation_id,
            )

        try:
            capability = self.context.capability_registry.resolve(command.name)
        except KeyError:
            return self._failure(
                command,
                CAPABILITY_NOT_FOUND_ERROR,
                UNKNOWN_COMMAND_MESSAGE,
                correlation_id=correlation_id,
            )

        try:
            result = capability.run(command, self.context)
        except Exception as error:
            logger.exception(
                "capability execution failed",
                extra={
                    "correlation_id": correlation_id,
                    "command": command.name,
                    "capability": command.name,
                },
            )
            return self._failure(
                command,
                CAPABILITY_EXECUTION_ERROR,
                RUNTIME_ERROR_MESSAGE,
                correlation_id=correlation_id,
                event_type=CAPABILITY_EXECUTION_FAILED_EVENT,
            )
        if not isinstance(result, CapabilityResult):
            logger.warning(
                "capability returned invalid result",
                extra={
                    "correlation_id": correlation_id,
                    "command": command.name,
                    "capability": command.name,
                    "result_type": type(result).__name__,
                },
            )
            return self._failure(
                command,
                INVALID_CAPABILITY_RESULT_ERROR,
                RUNTIME_ERROR_MESSAGE,
                correlation_id=correlation_id,
            )
        self._publish_event(
            type=CAPABILITY_EXECUTION_COMPLETED_EVENT,
            source="runtime",
            payload={
                "command": command.name,
                "capability": command.name,
                "success": result.success,
                "error": result.error,
            },
            correlation_id=correlation_id,
        )
        logger.info(
            "capability execution completed",
            extra={
                "correlation_id": correlation_id,
                "command": command.name,
                "capability": command.name,
                "success": result.success,
                "error": result.error,
            },
        )
        return result

    def _failure(
        self,
        command,
        error,
        message,
        correlation_id=None,
        event_type=RUNTIME_ERROR_EVENT,
    ):
        data = {
            "command": command.name,
            "source": command.source,
        }
        self._publish_event(
            type=event_type,
            source="runtime",
            payload={
                "command": command.name,
                "command_source": command.source,
                "error": error,
            },
            correlation_id=correlation_id,
        )
        logger.warning(
            "runtime command failure",
            extra={
                "correlation_id": correlation_id,
                "command": command.name,
                "command_source": command.source,
                "error": error,
            },
        )
        return CapabilityResult(
            success=False,
            message=message,
            data=data,
            error=error,
        )

    def _adapter_input_failure(self, source):
        return CapabilityResult(
            success=False,
            message=ADAPTER_INPUT_ERROR_MESSAGE,
            data={"source": source},
            error=INVALID_ADAPTER_INPUT_ERROR,
        )

    def _record_runtime_error(self, error, reason, correlation_id, source=None):
        self._publish_event(
            type=RUNTIME_ERROR_EVENT,
            source="runtime",
            payload={
                "source": source,
                "error": error,
                "reason": reason,
            },
            correlation_id=correlation_id,
        )
        logger.warning(
            "runtime adapter input failure",
            extra={
                "correlation_id": correlation_id,
                "source": source,
                "error": error,
                "reason": reason,
            },
        )

    def _publish_event(self, type, source, payload, correlation_id=None):
        event = Event(
            type=type,
            source=source,
            payload=payload,
            correlation_id=correlation_id,
        )
        self.context.event_bus.publish(event)
        return event

    def _new_correlation_id(self):
        return str(uuid4())


def build_runtime():
    """Wire the minimal AVP-001 core and return its Runtime boundary."""
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
    return runtime
