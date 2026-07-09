import unittest

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.devices import DeviceRegistry
from jarvis_core.domain import CapabilityResult, Command, Event, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.runtime import (
    CAPABILITY_EXECUTION_ERROR,
    CAPABILITY_NOT_FOUND_ERROR,
    INVALID_CAPABILITY_RESULT_ERROR,
    UNKNOWN_COMMAND_ERROR,
    Runtime,
    build_runtime,
)


class FailingCapability:
    name = "failing.capability"

    def run(self, command, context):
        raise RuntimeError("boom")


class InvalidResultCapability:
    name = "invalid.result"

    def run(self, command, context):
        return "not a capability result"


class RuntimeTest(unittest.TestCase):
    def build_test_runtime(self):
        bus = EventBus()
        registry = CapabilityRegistry()
        registry.register(ClockCapability.name, ClockCapability())
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        return Runtime(Planner(), context)

    def test_execute_runs_registered_capability(self):
        runtime = self.build_test_runtime()

        result = runtime.execute(Command(name="time.now"))

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertTrue(result.message.startswith("The current time is "))

    def test_execute_unknown_command_returns_failure_result(self):
        runtime = self.build_test_runtime()

        result = runtime.execute(Command(name="unknown", args={"text": "unknown"}))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "I do not know how to handle that yet.")
        self.assertEqual(result.error, UNKNOWN_COMMAND_ERROR)
        self.assertEqual(
            result.data,
            {"command": "unknown", "args": {"text": "unknown"}, "source": "cli"},
        )

    def test_execute_missing_capability_returns_structured_failure_result(self):
        runtime = self.build_test_runtime()

        result = runtime.execute(Command(name="missing.capability", source="test"))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "I do not know how to handle that yet.")
        self.assertEqual(result.error, CAPABILITY_NOT_FOUND_ERROR)
        self.assertEqual(
            result.data,
            {"command": "missing.capability", "args": {}, "source": "test"},
        )

    def test_execute_capability_exception_returns_structured_failure_result(self):
        bus = EventBus()
        registry = CapabilityRegistry()
        registry.register("failing.capability", FailingCapability())
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(Planner(), context)

        result = runtime.execute(Command(name="failing.capability"))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "I could not complete that command.")
        self.assertEqual(result.error, CAPABILITY_EXECUTION_ERROR)
        self.assertEqual(result.data["command"], "failing.capability")
        self.assertEqual(result.data["args"], {})
        self.assertEqual(result.data["source"], "cli")
        self.assertEqual(result.data["details"], "boom")

    def test_execute_invalid_capability_result_returns_structured_failure(self):
        bus = EventBus()
        registry = CapabilityRegistry()
        registry.register("invalid.result", InvalidResultCapability())
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(Planner(), context)

        result = runtime.execute(Command(name="invalid.result"))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "I could not complete that command.")
        self.assertEqual(result.error, INVALID_CAPABILITY_RESULT_ERROR)
        self.assertEqual(result.data["command"], "invalid.result")
        self.assertEqual(result.data["details"], "Capability returned an invalid result")

    def test_clock_capability_satisfies_capability_contract(self):
        capability = ClockCapability()

        self.assertIsInstance(capability.name, str)
        self.assertTrue(capability.name)
        self.assertTrue(callable(capability.run))
        self.assertIsInstance(capability.run(Command(name="time.now")), CapabilityResult)

    def test_build_runtime_preserves_avp_001_bus_response(self):
        bus = build_runtime()

        responses = bus.publish(
            Event(
                type="user.input.received",
                source="cli",
                payload={"text": "what time is it?"},
            )
        )

        self.assertEqual(len(responses), 1)
        self.assertTrue(responses[0].startswith("The current time is "))

    def test_build_runtime_subscribes_to_user_input_received_event(self):
        bus = build_runtime()

        responses = bus.publish(
            Event(
                type="user.input.received",
                source="cli",
                payload={"text": "que hora es?"},
            )
        )

        self.assertEqual(len(responses), 1)
        self.assertTrue(responses[0].startswith("The current time is "))

    def test_handle_user_input_preserves_adapter_message_boundary(self):
        runtime = self.build_test_runtime()

        message = runtime.handle_user_input("what time is it?")

        self.assertTrue(message.startswith("The current time is "))

    def test_runtime_context_includes_device_registry(self):
        bus = EventBus()
        registry = CapabilityRegistry()
        device_registry = DeviceRegistry()

        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=device_registry,
        )

        self.assertIs(context.device_registry, device_registry)


if __name__ == "__main__":
    unittest.main()
