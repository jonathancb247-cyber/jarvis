import unittest

from jarvis_core.cli import run_cli
from jarvis_core.runtime import build_runtime


class InteractiveCliTest(unittest.TestCase):
    def test_cli_processes_input_until_exit(self):
        inputs = iter(["what time is it?", "exit"])
        output = []

        def input_fn(prompt):
            output.append(prompt)
            return next(inputs)

        run_cli(build_runtime(), input_fn=input_fn, output_fn=output.append)

        self.assertEqual(output[0], "Jarvis AVP-001")
        self.assertEqual(output[1], "jarvis> ")
        self.assertTrue(output[2].startswith("Jarvis: The current time is "))
        self.assertEqual(output[3], "jarvis> ")
        self.assertEqual(output[4], "Bye.")

    def test_cli_ignores_blank_input(self):
        inputs = iter(["", "exit"])
        output = []

        def input_fn(prompt):
            output.append(prompt)
            return next(inputs)

        run_cli(build_runtime(), input_fn=input_fn, output_fn=output.append)

        self.assertEqual(
            output,
            ["Jarvis AVP-001", "jarvis> ", "jarvis> ", "Bye."],
        )

    def test_cli_exits_on_eof(self):
        output = []

        def input_fn(prompt):
            output.append(prompt)
            raise EOFError

        run_cli(build_runtime(), input_fn=input_fn, output_fn=output.append)

        self.assertEqual(output, ["Jarvis AVP-001", "jarvis> ", "Bye."])


if __name__ == "__main__":
    unittest.main()
