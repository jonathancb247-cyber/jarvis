import unittest

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.devices import DeviceRegistry
from jarvis_core.domain import CapabilityResult, Command, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.runtime import (
    ADAPTER_INPUT_ERROR_MESSAGE,
    CAPABILITY_EXECUTION_ERROR,
    CAPABILITY_NOT_FOUND_ERROR,
    INVALID_ADAPTER_INPUT_ERROR,
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


class RecordingPlanner:
    def __init__(self, command):
        self.command = command
        self.calls = []

    def plan(self, text, source="cli"):
        self.calls.append({"text": text, "source": source})
        return self.command


class RecordingEventBus(EventBus):
    def __init__(self):
        super().__init__()
        self.published = []

    def publish(self, event):
        self.published.append(event)
        return super().publish(event)


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
            {"command": "unknown", "source": "cli"},
        )

    def test_execute_missing_capability_returns_structured_failure_result(self):
        runtime = self.build_test_runtime()

        result = runtime.execute(Command(name="missing.capability", source="test"))

        self.assertFalse(result.success)
        self.assertEqual(result.message, "I do not know how to handle that yet.")
        self.assertEqual(result.error, CAPABILITY_NOT_FOUND_ERROR)
        self.assertEqual(
            result.data,
            {"command": "missing.capability", "source": "test"},
        )

    def test_execute_capability_exception_returns_structured_failure_result(self):
        bus = RecordingEventBus()
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
        self.assertEqual(result.data["source"], "cli")
        self.assertNotIn("args", result.data)
        self.assertNotIn("details", result.data)
        self.assertEqual(bus.published[-1].type, "capability.execution.failed")
        self.assertEqual(bus.published[-1].payload["error"], CAPABILITY_EXECUTION_ERROR)

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
        self.assertNotIn("args", result.data)
        self.assertNotIn("details", result.data)

    def test_clock_capability_satisfies_capability_contract(self):
        capability = ClockCapability()

        self.assertIsInstance(capability.name, str)
        self.assertTrue(capability.name)
        self.assertTrue(callable(capability.run))
        self.assertIsInstance(capability.run(Command(name="time.now")), CapabilityResult)

    def test_build_runtime_returns_runtime_adapter_boundary(self):
        runtime = build_runtime()

        result = runtime.handle_adapter_input("what time is it?", source="cli")

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertTrue(result.message.startswith("The current time is "))

    def test_build_runtime_registers_device_catalog_capability(self):
        runtime = build_runtime()

        result = runtime.handle_adapter_input("device list", source="cli")

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertEqual(result.message, "No devices registered.")
        self.assertEqual(result.data, {"count": 0, "devices": []})

    def test_build_runtime_registers_device_lifecycle_capability(self):
        runtime = build_runtime()

        result = runtime.handle_adapter_input(
            "device add lamp_1 name=Lamp type=light",
            source="cli",
        )

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertEqual(result.message, "Device registered.")
        self.assertEqual(result.data, {"operation": "add", "device_id": "lamp_1"})

    def test_runtime_device_lifecycle_add_then_catalog_list(self):
        runtime = build_runtime()

        runtime.handle_adapter_input("device add lamp_1 name=Lamp type=light")
        result = runtime.handle_adapter_input("device list")

        self.assertTrue(result.success)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["devices"][0]["id"], "lamp_1")

    def test_runtime_device_lifecycle_add_then_catalog_info(self):
        runtime = build_runtime()

        runtime.handle_adapter_input("device add lamp_1 name=Lamp type=light")
        result = runtime.handle_adapter_input("device info lamp_1")

        self.assertTrue(result.success)
        self.assertEqual(result.data["device"]["id"], "lamp_1")
        self.assertEqual(result.data["device"]["name"], "Lamp")
        self.assertEqual(result.data["device"]["type"], "light")

    def test_runtime_device_lifecycle_remove_then_catalog_list(self):
        runtime = build_runtime()

        runtime.handle_adapter_input("device add lamp_1 name=Lamp type=light")
        remove_result = runtime.handle_adapter_input("device remove lamp_1")
        list_result = runtime.handle_adapter_input("device list")

        self.assertTrue(remove_result.success)
        self.assertEqual(remove_result.message, "Device removed.")
        self.assertTrue(list_result.success)
        self.assertEqual(list_result.data, {"count": 0, "devices": []})

    def test_runtime_device_lifecycle_remove_then_catalog_not_found(self):
        runtime = build_runtime()

        runtime.handle_adapter_input("device add lamp_1 name=Lamp type=light")
        runtime.handle_adapter_input("device remove lamp_1")
        result = runtime.handle_adapter_input("device info lamp_1")

        self.assertFalse(result.success)
        self.assertEqual(result.error, "device_not_found")

    def test_runtime_device_lifecycle_does_not_expose_full_command_args(self):
        runtime = build_runtime()

        result = runtime.handle_adapter_input(
            "device add lamp_1 name=SecretName type=secret_type",
            source="cli",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data, {"operation": "add", "device_id": "lamp_1"})
        self.assertNotIn("SecretName", str(result.data))
        self.assertNotIn("secret_type", str(result.data))

    def test_handle_user_input_preserves_adapter_message_boundary(self):
        runtime = self.build_test_runtime()

        message = runtime.handle_user_input("what time is it?")

        self.assertTrue(message.startswith("The current time is "))

    def test_handle_adapter_input_returns_capability_result(self):
        runtime = self.build_test_runtime()

        result = runtime.handle_adapter_input("que hora es?", source="cli")

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertTrue(result.message.startswith("The current time is "))

    def test_handle_adapter_input_passes_source_to_planner(self):
        planner = RecordingPlanner(Command(name="unknown", args={}, source="api"))
        bus = EventBus()
        registry = CapabilityRegistry()
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(planner, context)

        result = runtime.handle_adapter_input("hello", source="api")

        self.assertEqual(planner.calls, [{"text": "hello", "source": "api"}])
        self.assertFalse(result.success)
        self.assertEqual(result.data, {"command": "unknown", "source": "api"})

    def test_handle_adapter_input_emits_lifecycle_events_with_correlation_id(self):
        bus = RecordingEventBus()
        registry = CapabilityRegistry()
        registry.register(ClockCapability.name, ClockCapability())
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(Planner(), context)

        runtime.handle_adapter_input("what time is it?", source="cli")

        self.assertEqual(
            [event.type for event in bus.published],
            [
                "user.input.received",
                "command.planned",
                "command.execution.started",
                "capability.execution.completed",
            ],
        )
        correlation_id = bus.published[0].correlation_id
        self.assertTrue(correlation_id)
        self.assertTrue(
            all(event.correlation_id == correlation_id for event in bus.published)
        )
        self.assertEqual(bus.published[0].source, "cli")
        self.assertEqual(bus.published[0].payload, {"input_length": 16})
        self.assertNotIn("text", bus.published[0].payload)

    def test_handle_adapter_input_does_not_log_full_input_text(self):
        bus = RecordingEventBus()
        registry = CapabilityRegistry()
        registry.register(ClockCapability.name, ClockCapability())
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(Planner(), context)

        with self.assertLogs("jarvis_core.runtime", level="INFO") as logs:
            runtime.handle_adapter_input("secret token value", source="cli")

        output = "\n".join(logs.output)
        self.assertNotIn("secret token value", output)
        self.assertEqual(bus.published[0].payload, {"input_length": 18})

    def test_handle_adapter_input_controlled_failure_emits_runtime_error(self):
        bus = RecordingEventBus()
        registry = CapabilityRegistry()
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(Planner(), context)

        result = runtime.handle_adapter_input("turn on lights", source="cli")

        self.assertFalse(result.success)
        self.assertEqual(result.error, UNKNOWN_COMMAND_ERROR)
        self.assertEqual(bus.published[-1].type, "runtime.error")
        self.assertEqual(bus.published[-1].payload["error"], UNKNOWN_COMMAND_ERROR)

    def test_unknown_command_text_is_not_exposed_to_adapter(self):
        bus = RecordingEventBus()
        registry = CapabilityRegistry()
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(Planner(), context)

        with self.assertLogs("jarvis_core.runtime", level="INFO") as logs:
            result = runtime.handle_adapter_input("secret token value", source="cli")

        self.assertFalse(result.success)
        self.assertNotIn("secret token value", str(result.data))
        self.assertNotIn("args", result.data)
        self.assertNotIn("secret token value", "\n".join(logs.output))
        self.assertTrue(
            all("secret token value" not in str(event.payload) for event in bus.published)
        )

    def test_invalid_device_input_does_not_expose_raw_text(self):
        bus = RecordingEventBus()
        registry = CapabilityRegistry()
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(Planner(), context)

        with self.assertLogs("jarvis_core.runtime", level="INFO") as logs:
            result = runtime.handle_adapter_input(
                "device apply secret-device power token",
                source="cli",
            )

        self.assertFalse(result.success)
        self.assertNotIn("secret-device", str(result.data))
        self.assertNotIn("token", str(result.data))
        self.assertNotIn("secret-device", "\n".join(logs.output))
        self.assertNotIn("token", "\n".join(logs.output))
        self.assertTrue(
            all("secret-device" not in str(event.payload) for event in bus.published)
        )
        self.assertTrue(all("token" not in str(event.payload) for event in bus.published))

    def test_handle_adapter_input_rejects_non_text_input(self):
        bus = RecordingEventBus()
        registry = CapabilityRegistry()
        registry.register(ClockCapability.name, ClockCapability())
        context = RuntimeContext(
            event_bus=bus,
            capability_registry=registry,
            device_registry=DeviceRegistry(),
        )
        runtime = Runtime(Planner(), context)

        result = runtime.handle_adapter_input(None, source="cli")

        self.assertFalse(result.success)
        self.assertEqual(result.message, ADAPTER_INPUT_ERROR_MESSAGE)
        self.assertEqual(result.error, INVALID_ADAPTER_INPUT_ERROR)
        self.assertEqual(bus.published[-1].type, "runtime.error")

    def test_handle_adapter_input_rejects_empty_source(self):
        runtime = self.build_test_runtime()

        result = runtime.handle_adapter_input("what time is it?", source="")

        self.assertFalse(result.success)
        self.assertEqual(result.message, ADAPTER_INPUT_ERROR_MESSAGE)
        self.assertEqual(result.error, INVALID_ADAPTER_INPUT_ERROR)

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
