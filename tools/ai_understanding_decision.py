"""Opt-in non-executing local understanding decision helper.

Runs one local Gemma understanding extraction through normalization, the
existing DeterministicUnderstandingResolver, and the existing validation /
Planner boundary, then reports a LocalUnderstandingDecision. Evaluation and
diagnostic tooling only: it never executes Runtime, Drivers, tools, STT,
Voice, or a cloud fallback, and never exposes execution flags.

The device context is a fixed deterministic two-lamp fixture so results are
stable without a running Registry. The --model value is a lab label only: the
operator must load the intended on-device artifact before running. Canonical
command text is hidden unless --show-canonical is passed explicitly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jarvis_core.ai.contracts import (  # noqa: E402
    MAX_PLAN_STEPS,
    PLAN_SCHEMA_VERSION,
    AISafeCapability,
    AISafeContext,
    AISafeDevice,
    AISafeDeviceState,
    AISafePolicyContext,
)
from jarvis_core.ai.context import command_grammar_catalog  # noqa: E402
from jarvis_core.ai.gemma_android_bridge import (  # noqa: E402
    DEFAULT_ANDROID_BRIDGE_PORT,
    GemmaAndroidBridgeConfig,
    GemmaAndroidBridgeTransport,
)
from jarvis_core.ai.gemma_understanding import (  # noqa: E402
    GemmaLocalUnderstandingProvider,
    GemmaUnderstandingProviderConfig,
)
from jarvis_core.ai.understanding_decision import decide_understanding  # noqa: E402
from jarvis_core.ai.understanding_diagnostic import (  # noqa: E402
    describe_decision,
    describe_execution_state,
)

DEFAULT_DECISION_MODEL = "gemma3-1b-it-int4.litertlm"


def run_ai_understanding_decision(
    request: str,
    *,
    model: str = DEFAULT_DECISION_MODEL,
    host: str = "127.0.0.1",
    port: int = DEFAULT_ANDROID_BRIDGE_PORT,
    timeout_seconds: int = 60,
    maximum_output_tokens: int = 256,
    show_canonical: bool = False,
    transport=None,
    clock=perf_counter,
) -> dict[str, object]:
    request = request.strip()
    if not request:
        raise ValueError("--request is required")
    provider = GemmaLocalUnderstandingProvider(
        GemmaUnderstandingProviderConfig(
            model=model,
            timeout_seconds=timeout_seconds,
            maximum_output_tokens=maximum_output_tokens,
        ),
        transport=transport
        or GemmaAndroidBridgeTransport(GemmaAndroidBridgeConfig(host=host, port=port)),
    )
    context = decision_fixture_context(request)
    decision = decide_understanding(
        provider,
        context,
        provider_id="gemma-local-understanding",
        model_id=model,
        clock=clock,
    )
    return {
        "provider": "gemma-local-understanding",
        "model": model,
        "fixture_set": "ai-understanding-decision-local-fixture",
        "execution": describe_execution_state(),
        "decision": describe_decision(decision, show_canonical=show_canonical),
    }


def decision_fixture_context(request: str) -> AISafeContext:
    """Fixed deterministic two-lamp fixture context (no Registry required)."""
    return AISafeContext(
        schema_version=PLAN_SCHEMA_VERSION,
        user_request=request,
        devices=(
            _safe_lamp("lamp_1", "Lamp"),
            _safe_lamp("lamp_2", "Desk Lamp"),
        ),
        command_grammar=command_grammar_catalog(),
        policies=AISafePolicyContext(
            max_plan_steps=MAX_PLAN_STEPS,
            confirmation_required_for_mutations=True,
        ),
    )


def _safe_lamp(device_id: str, display_name: str) -> AISafeDevice:
    return AISafeDevice(
        device_id=device_id,
        display_name=display_name,
        device_type="light",
        capabilities=(
            AISafeCapability("status.read", "reading", ()),
            AISafeCapability(
                "power.switch",
                "action",
                ({"name": "state", "type": "string", "required": True},),
            ),
        ),
        state=AISafeDeviceState("known", (("power", False),), None),
    )


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        payload = run_ai_understanding_decision(
            args.request,
            model=args.model,
            host=args.host,
            port=args.port,
            timeout_seconds=args.timeout_seconds,
            maximum_output_tokens=args.max_output_tokens,
            show_canonical=args.show_canonical,
            clock=perf_counter,
        )
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print("decision:")
    print(format_decision_text_payload(payload, show_canonical=args.show_canonical))
    return 0


def format_decision_text_payload(payload: dict[str, object], *, show_canonical: bool) -> str:
    """Render the CLI decision payload without re-running the decision."""
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        return "decision unavailable"
    lines = [
        f"provider_id: {decision.get('provider_id') or 'null'}",
        f"model_id: {decision.get('model_id') or 'null'}",
        f"status: {decision.get('status') or 'null'}",
        f"proposal_valid: {str(bool(decision.get('proposal_valid'))).lower()}",
        f"resolver_kind: {decision.get('resolver_kind') or 'null'}",
        f"planner_kind: {decision.get('planner_kind') or 'null'}",
        f"confirmation_required: {str(bool(decision.get('confirmation_required'))).lower()}",
        f"latency_ms: {_optional_int(decision.get('latency_ms'))}",
        f"failure_stage: {decision.get('failure_stage') or 'null'}",
        f"failure_category: {decision.get('failure_category') or 'null'}",
        "commands_executed: false",
    ]
    if decision.get("safe_summary"):
        lines.append(f"safe_summary: {decision['safe_summary']}")
    clarification = decision.get("clarification")
    if isinstance(clarification, dict) and clarification.get("question"):
        lines.append(
            "clarification: "
            f"{clarification['question']} (reason: {clarification.get('reason_code')})"
        )
    refusal = decision.get("refusal")
    if isinstance(refusal, dict) and refusal.get("safe_message"):
        lines.append(
            f"refusal: {refusal['safe_message']} (reason: {refusal.get('reason_code')})"
        )
    if show_canonical and decision.get("canonical_command_text"):
        lines.append(f"canonical_command: {decision['canonical_command_text']}")
        if decision.get("safe_description"):
            lines.append(f"safe_description: {decision['safe_description']}")
    return "\n".join(lines)


def _optional_int(value) -> str:
    if value is None:
        return "null"
    return str(value)


def _parse_args(argv=None):
    parser = build_argument_parser()
    return parser.parse_args(argv)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Non-executing local understanding decision helper",
        epilog=(
            "Load the intended on-device artifact before running; --model is a "
            "lab label only. This tool never executes commands, Runtime, "
            "Drivers, STT, Voice, or a cloud fallback. Canonical commands are "
            "hidden unless --show-canonical is passed."
        ),
    )
    parser.add_argument("--request", required=True, metavar="TEXT", help="User request to understand")
    parser.add_argument("--model", default=DEFAULT_DECISION_MODEL, help="Lab label of the loaded artifact")
    parser.add_argument("--host", default="127.0.0.1", help="Local Android bridge host")
    parser.add_argument("--port", type=int, default=DEFAULT_ANDROID_BRIDGE_PORT, help="Local Android bridge port")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument("--show-canonical", action="store_true", help="Show canonical command text explicitly")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())