import unittest

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry


class PlannerTest(unittest.TestCase):
    def test_plan_resolves_time_intent_in_english(self):
        planner = Planner(CapabilityRegistry())

        self.assertEqual(planner.plan("what time is it?"), "time.now")

    def test_plan_resolves_time_intent_in_spanish(self):
        planner = Planner(CapabilityRegistry())

        self.assertEqual(planner.plan("que hora es?"), "time.now")

    def test_execute_unknown_intent_returns_fallback(self):
        planner = Planner(CapabilityRegistry())

        self.assertEqual(
            planner.execute("turn on the lights"),
            "I do not know how to handle that yet.",
        )

    def test_execute_time_intent_runs_registered_capability(self):
        registry = CapabilityRegistry()
        registry.register(ClockCapability.name, ClockCapability())
        planner = Planner(registry)

        response = planner.execute("what time is it?")

        self.assertTrue(response.startswith("The current time is "))
        self.assertTrue(response.endswith("."))


if __name__ == "__main__":
    unittest.main()
