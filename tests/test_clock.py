import unittest

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.domain import CapabilityResult, Command


class ClockCapabilityTest(unittest.TestCase):
    def test_run_returns_capability_result(self):
        result = ClockCapability().run(Command(name="time.now"))

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertRegex(result.message, r"^The current time is \d{2}:\d{2}\.$")
        self.assertRegex(result.data["time"], r"^\d{2}:\d{2}$")
        self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
