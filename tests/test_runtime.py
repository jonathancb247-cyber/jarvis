import unittest

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.domain import CapabilityResult, Command, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.runtime import Runtime, build_runtime


class RuntimeTest(unittest.TestCase):
    def build_test_runtime(self):
        bus = EventBus()
        registry = CapabilityRegistry()
        registry.register(ClockCapability.name, ClockCapability())
        context = RuntimeContext(event_bus=bus, capability_registry=registry)
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
        self.assertEqual(result.error, "unknown_command")

    def test_build_runtime_preserves_avp_001_bus_response(self):
        bus = build_runtime()

        responses = bus.publish("user.input", {"text": "what time is it?"})

        self.assertEqual(len(responses), 1)
        self.assertTrue(responses[0].startswith("The current time is "))


if __name__ == "__main__":
    unittest.main()
