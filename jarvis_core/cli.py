"""Interactive command-line interface for JarvisOS AVP-001."""


EXIT_COMMANDS = {"exit", "quit"}
PROMPT = "jarvis> "


def run_cli(runtime, input_fn=input, output_fn=print):
    """Run the minimal interactive CLI loop."""
    output_fn("Jarvis AVP-001")

    while True:
        try:
            text = input_fn(PROMPT)
        except EOFError:
            output_fn("Bye.")
            break

        normalized = text.strip().lower()
        if normalized in EXIT_COMMANDS:
            output_fn("Bye.")
            break
        if not normalized:
            continue

        result = runtime.handle_adapter_input(text, source="cli")
        output_fn("Jarvis: " + result.message)
