import unittest

from jarvis_core.cli import CliAdapter, run_cli
from jarvis_core.domain import CapabilityResult
from jarvis_core.runtime import build_runtime


class FakeRuntime:
    def __init__(self, message="fake response"):
        self.message = message
        self.calls = []

    def handle_adapter_input(self, text, source="cli"):
        self.calls.append({"text": text, "source": source})
        return CapabilityResult(success=True, message=self.message)


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

    def test_cli_adapter_calls_runtime_boundary_with_cli_source(self):
        inputs = iter(["hello", "exit"])
        output = []
        runtime = FakeRuntime(message="ok")

        def input_fn(prompt):
            output.append(prompt)
            return next(inputs)

        CliAdapter(runtime, input_fn=input_fn, output_fn=output.append).run()

        self.assertEqual(runtime.calls, [{"text": "hello", "source": "cli"}])
        self.assertEqual(output[2], "Jarvis: ok")

    def test_cli_adapter_does_not_call_runtime_for_blank_input(self):
        inputs = iter(["", "exit"])
        output = []
        runtime = FakeRuntime()

        def input_fn(prompt):
            output.append(prompt)
            return next(inputs)

        CliAdapter(runtime, input_fn=input_fn, output_fn=output.append).run()

        self.assertEqual(runtime.calls, [])

    def test_run_cli_wraps_cli_adapter(self):
        inputs = iter(["hello", "quit"])
        output = []
        runtime = FakeRuntime(message="wrapped")

        def input_fn(prompt):
            output.append(prompt)
            return next(inputs)

        run_cli(runtime, input_fn=input_fn, output_fn=output.append)

        self.assertEqual(runtime.calls, [{"text": "hello", "source": "cli"}])
        self.assertEqual(output[2], "Jarvis: wrapped")


if __name__ == "__main__":
    unittest.main()
