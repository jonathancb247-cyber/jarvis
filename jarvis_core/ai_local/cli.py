"""Explicit Ollama local-AI composition root."""

from __future__ import annotations

import argparse

from jarvis_core.ai.adapter import FakeAIAdapter
from jarvis_core.ai.ollama import OllamaAIProvider, OllamaProviderConfig, OllamaProviderError
from jarvis_core.ai_cloud.cli import _print_result, _run_loop
from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.configuration import ConfigurationError
from jarvis_core.state_store import StateStoreError


def main(argv=None, input_fn=input, output_fn=print):
    args = _parse_args(argv)
    try:
        runtime = build_runtime_from_config(args.config)
        provider_config = OllamaProviderConfig(
            model=args.model,
            host=args.host,
            port=args.port,
            timeout_seconds=args.timeout_seconds,
        )
        provider = OllamaAIProvider(provider_config)
        adapter = FakeAIAdapter(runtime, provider)
    except ConfigurationError:
        output_fn("Configuration is invalid.")
        return 1
    except StateStoreError:
        output_fn("Device state could not be restored.")
        return 1
    except (ValueError, OllamaProviderError):
        output_fn("Ollama provider is unavailable.")
        return 1

    output_fn("JarvisOS AI local listening with provider ollama.")
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


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="python -m jarvis_core.ai_local")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an explicit JarvisOS runtime profile JSON file.",
    )
    parser.add_argument(
        "--provider",
        required=True,
        choices=["ollama"],
        help="Explicit local provider. No default provider is selected.",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Explicit local Ollama model to evaluate.",
    )
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost"])
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    return parser.parse_args(argv)


__all__ = ["main"]
