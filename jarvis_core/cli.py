"""Interactive command-line interface for JarvisOS AVP-001."""

from jarvis_core.domain import Event


EXIT_COMMANDS = {"exit", "quit"}
PROMPT = "jarvis> "


def run_cli(bus, input_fn=input, output_fn=print):
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

        event = Event(
            type="user.input.received",
            source="cli",
            payload={"text": text},
        )
        responses = bus.publish(event)
        for response in responses:
            output_fn("Jarvis: " + response)
