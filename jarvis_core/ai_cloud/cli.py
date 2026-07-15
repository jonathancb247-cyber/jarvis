"""Explicit cloud AI entry point for Groq validation."""

import argparse
import os

from jarvis_core.ai.adapter import FakeAIAdapter
from jarvis_core.ai.contracts import AI_CONFIRMATION_REQUIRED
from jarvis_core.ai.groq import (
    DEFAULT_GROQ_MODEL,
    GroqAIProvider,
    GroqProviderConfig,
)
from jarvis_core.ai.provider import AIProviderError
from jarvis_core.bootstrap import build_runtime_from_config


def build_ai_cloud_adapter(
    config_path,
    model=DEFAULT_GROQ_MODEL,
    api_key=None,
    transport=None,
):
    """Build the optional Groq-backed AI Adapter without default runtime wiring."""
    runtime = build_runtime_from_config(config_path)
    provider = GroqAIProvider(
        GroqProviderConfig(model=model),
        api_key=api_key,
        transport=transport,
    )
    return FakeAIAdapter(runtime, provider=provider)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m jarvis_core.ai_cloud",
        description="Run the explicit Groq-backed JarvisOS AI validation loop.",
    )
    parser.add_argument("--config", required=True, help="Runtime profile JSON path.")
    parser.add_argument(
        "--model",
        default=DEFAULT_GROQ_MODEL,
        help="Approved Groq model name.",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Groq API key is not configured. Set GROQ_API_KEY in this session.")
        return 1

    try:
        adapter = build_ai_cloud_adapter(args.config, args.model, api_key=api_key)
    except (AIProviderError, OSError, ValueError) as error:
        print(_safe_startup_error(error))
        return 1

    print("JarvisOS cloud AI validation started.")
    print("Type a Spanish request, confirm <plan_id>, cancel <plan_id>, or exit.")
    try:
        while True:
            user_input = input("ai-cloud> ").strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                break
            if user_input.lower().startswith("confirm "):
                result = adapter.confirm(user_input.split(None, 1)[1].strip())
            elif user_input.lower().startswith("cancel "):
                result = adapter.cancel(user_input.split(None, 1)[1].strip())
            else:
                result = adapter.propose(user_input)
            _print_result(result)
    except KeyboardInterrupt:
        print()
    finally:
        shutdown = getattr(adapter.runtime, "shutdown", None)
        if callable(shutdown):
            shutdown()
    return 0


def _print_result(result):
    print(f"status: {result.status}")
    if result.error:
        print(f"error: {result.error}")
    if result.message:
        print(f"message: {result.message}")
    if result.plan is not None:
        print(f"plan_kind: {result.plan.kind}")
        if result.plan.safe_summary:
            print(f"summary: {result.plan.safe_summary}")
        for step in result.plan.steps:
            print(f"command: {step.canonical_command_text}")
    if result.error == AI_CONFIRMATION_REQUIRED:
        print("confirmation_required: true")
    if result.clarification is not None:
        print(f"clarification: {result.clarification.question}")
    if result.refusal is not None:
        print(f"refusal: {result.refusal.safe_message}")
    if result.execution_summary is not None:
        print(f"execution_success: {result.execution_summary.overall_success}")
        print(f"execution_message: {result.execution_summary.safe_message}")


def _safe_startup_error(error):
    if isinstance(error, AIProviderError):
        return f"Cloud AI provider unavailable: {error.code}"
    return "Cloud AI startup failed safely."
