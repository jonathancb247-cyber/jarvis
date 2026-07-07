import unittest

from jarvis_core.capabilities.clock import ClockCapability


class ClockCapabilityTest(unittest.TestCase):
    def test_run_returns_time_response(self):
        response = ClockCapability().run()

        self.assertRegex(response, r"^The current time is \d{2}:\d{2}\.$")


if __name__ == "__main__":
    unittest.main()
