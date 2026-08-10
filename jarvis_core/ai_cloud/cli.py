"""Explicit Gemini cloud-AI composition root."""

import argparse

from jarvis_core.ai.adapter import FakeAIAdapter
from jarvis_core.ai.gemini import (
    DEFAULT_GEMINI_MODEL,
    GEMINI_API_KEY_ENV,
    SUPPORTED_GEMINI_MODELS,
    GeminiAIProvider,
    GeminiProviderConfig,
    GeminiProviderError,
)
from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.configuration import ConfigurationError
from jarvis_core.state_store import StateStoreError


EXIT_COMMANDS = {"exit", "quit"}
CONFIRM_PREFIX = "confirm "
CANCEL_PREFIX = "cancel "


def main(argv=None, input_fn=input, output_fn=print):
    args = _parse_args(argv)
    try:
        runtime = build_runtime_from_config(args.config)
        config = GeminiProviderConfig(model=args.model)
        provider = GeminiAIProvider.from_environment(config=config)
        adapter = FakeAIAdapter(runtime, provider)
    except ConfigurationError:
        output_fn("Configuration is invalid.")
        return 1
    except StateStoreError:
        output_fn("Device state could not be restored.")
        return 1
    except (ValueError, GeminiProviderError):
        output_fn("Gemini provider is unavailable.")
        return 1

    output_fn("JarvisOS AI cloud listening with provider gemini.")
    try:
        _run_loop(adapter, input_fn, output_fn)
    finally:
        shutdown = getattr(runtime, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                output_fn("Device state could not be saved.")
    return 0


def _run_loop(adapter, input_fn, output_fn):
    while True:
        try:
            text = input_fn("jarvis-ai> ")
        except EOFError:
            output_fn("Bye.")
            return
        normalized = text.strip()
        lowered = normalized.lower()
        if lowered in EXIT_COMMANDS:
            output_fn("Bye.")
            return
        if not normalized:
            continue
        if lowered.startswith(CONFIRM_PREFIX):
            result = adapter.confirm(normalized[len(CONFIRM_PREFIX) :].strip())
        elif lowered.startswith(CANCEL_PREFIX):
            result = adapter.cancel(normalized[len(CANCEL_PREFIX) :].strip())
        else:
            result = adapter.propose(normalized)
        _print_result(result, output_fn)


def _print_result(result, output_fn):
    if result.status == "confirmation_required":
        output_fn("Confirmation required.")
        output_fn(result.message)
        for step in result.plan.steps:
            output_fn(step.canonical_command_text)
        return
    if result.status == "clarification_required":
        output_fn(result.message)
        return
    if result.status == "refused":
        output_fn(result.message)
        return
    if result.status == "executed":
        output_fn(result.message)
        return
    output_fn("AI adapter request failed.")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jarvis_core.ai_cloud")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an explicit JarvisOS runtime profile JSON file.",
    )
    parser.add_argument(
        "--provider",
        required=True,
        choices=["gemini"],
        help="Explicit cloud provider. No default provider is selected.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_GEMINI_MODEL,
        choices=sorted(SUPPORTED_GEMINI_MODELS),
        help="Approved Gemini model for this experimental provider.",
    )
    parser.epilog = f"Load {GEMINI_API_KEY_ENV} in the active shell; never pass it as an argument."
    return parser.parse_args(argv)
