"""Minimal explicit AI-local interaction loop for manual validation."""

import argparse
import signal

from jarvis_core.ai import FakeAIAdapter
from jarvis_core.ai.ollama import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    OllamaAIProvider,
    OllamaProviderConfig,
)
from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.configuration import ConfigurationError
from jarvis_core.state_store import StateStoreError


def main(argv=None):
    _install_signal_handlers()
    args = _parse_args(argv)
    runtime = None
    try:
        runtime = build_runtime_from_config(args.config)
        provider = OllamaAIProvider(
            OllamaProviderConfig(
                model=args.model,
                base_url=args.base_url,
                timeout_seconds=args.timeout,
                maximum_response_bytes=args.maximum_response_bytes,
            ),
            diagnostic_enabled=args.diagnostic,
        )
        adapter = FakeAIAdapter(runtime, provider=provider)
    except ConfigurationError:
        print("Configuration is invalid.")
        return 1
    except StateStoreError:
        print("Device state could not be restored.")
        return 1
    except (TypeError, ValueError):
        print("Local AI configuration is invalid.")
        return 1

    print("JarvisOS AI-local adapter listening for local requests.")
    print("Type a Spanish request, 'confirm <plan_id>', 'cancel <plan_id>', or 'exit'.")
    try:
        _interaction_loop(adapter, provider)
    except KeyboardInterrupt:
        pass
    finally:
        runtime.shutdown()
    return 0


def _interaction_loop(adapter, provider):
    while True:
        user_input = input("ai> ").strip()
        if not user_input:
            continue
        lowered = user_input.lower()
        if lowered in {"exit", "quit"}:
            print("Bye.")
            return
        if lowered.startswith("confirm "):
            _print_result(adapter.confirm(user_input.split(maxsplit=1)[1].strip()))
            _print_diagnostics(provider)
            continue
        if lowered.startswith("cancel "):
            _print_result(adapter.cancel(user_input.split(maxsplit=1)[1].strip()))
            _print_diagnostics(provider)
            continue
        _print_result(adapter.propose(user_input))
        _print_diagnostics(provider)


def _print_result(result):
    print(f"status: {result.status}")
    if result.message:
        print(f"message: {result.message}")
    if result.error:
        print(f"error: {result.error}")
    if result.plan is not None and result.plan.safe_summary:
        print(f"summary: {result.plan.safe_summary}")
    if result.plan is not None and result.plan.steps:
        print("steps:")
        for step in result.plan.steps:
            print(f"  {step.index}: {step.canonical_command_text}")
    if result.execution_summary is not None:
        print(f"completed_steps: {result.execution_summary.completed_steps}")
        print(f"overall_success: {result.execution_summary.overall_success}")
    if result.clarification is not None:
        print(f"question: {result.clarification.question}")
    if result.refusal is not None:
        print(f"refusal: {result.refusal.safe_message}")


def _print_diagnostics(provider):
    consume = getattr(provider, "consume_diagnostics", None)
    if not callable(consume):
        return
    diagnostics = consume()
    if not diagnostics:
        return
    print("diagnostic:")
    for item in diagnostics:
        parts = []
        for key in sorted(item):
            parts.append(f"{key}={item[key]}")
        print("  " + " ".join(parts))


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jarvis_core.ai_local")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an explicit JarvisOS runtime profile JSON file.",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Explicit local Ollama model name, for example qwen3:1.7b.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help="Localhost Ollama base URL.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        help="Provider timeout in seconds.",
    )
    parser.add_argument(
        "--maximum-response-bytes",
        type=int,
        default=262144,
        help="Maximum Ollama response size.",
    )
    parser.add_argument(
        "--diagnostic",
        action="store_true",
        help="Print safe provider stage diagnostics without raw prompts or responses.",
    )
    return parser.parse_args(argv)


def _install_signal_handlers():
    def interrupt(signum, frame):
        raise KeyboardInterrupt

    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, interrupt)
