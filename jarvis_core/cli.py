"""Interactive command-line interface for JarvisOS AVP-001."""


EXIT_COMMANDS = {"exit", "quit"}
PROMPT = "jarvis> "
SHUTDOWN_SAVE_ERROR_MESSAGE = "Device state could not be saved."


class CliAdapter:
    """Command-line adapter for the Runtime-owned adapter boundary."""

    def __init__(self, runtime, input_fn=input, output_fn=print):
        self.runtime = runtime
        self.input_fn = input_fn
        self.output_fn = output_fn

    def run(self):
        """Run the minimal interactive CLI loop."""
        self.output_fn("Jarvis AVP-001")

        while True:
            try:
                text = self.input_fn(PROMPT)
            except EOFError:
                self._shutdown()
                self.output_fn("Bye.")
                break

            normalized = text.strip().lower()
            if normalized in EXIT_COMMANDS:
                self._shutdown()
                self.output_fn("Bye.")
                break
            if not normalized:
                continue

            result = self.runtime.handle_adapter_input(text, source="cli")
            self.output_fn("Jarvis: " + result.message)

    def _shutdown(self):
        shutdown = getattr(self.runtime, "shutdown", None)
        if not callable(shutdown):
            return
        try:
            shutdown()
        except Exception:
            self.output_fn(SHUTDOWN_SAVE_ERROR_MESSAGE)


def run_cli(runtime, input_fn=input, output_fn=print):
    """Run the CLI adapter with the minimal AVP-001 loop."""
    CliAdapter(runtime, input_fn=input_fn, output_fn=output_fn).run()
