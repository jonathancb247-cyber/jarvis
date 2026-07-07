import unittest

from jarvis_core.domain import Command
from jarvis_core.planner import Planner


class PlannerTest(unittest.TestCase):
    def test_plan_returns_time_command_in_english(self):
        command = Planner().plan("what time is it?")

        self.assertEqual(command, Command(name="time.now", args={}, source="cli"))

    def test_plan_returns_time_command_in_spanish(self):
        command = Planner().plan("que hora es?")

        self.assertEqual(command, Command(name="time.now", args={}, source="cli"))

    def test_plan_returns_unknown_command_for_unknown_input(self):
        command = Planner().plan("turn on the lights")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"text": "turn on the lights"})
        self.assertEqual(command.source, "cli")


if __name__ == "__main__":
    unittest.main()
