"""Opt-in safe local understanding execution demo helper.

Runs one deterministic understanding extraction through normalization, the
existing DeterministicUnderstandingResolver, the planned ExecutionGate, and a
simulated in-memory Runtime/Driver. This demonstrates the thesis vertical:

    user request -> safe context -> understanding provider
    -> LocalUnderstandingDecision -> ExecutionGate -> Runtime -> simulated DeviceState

The provider is a keyword-based deterministic demo (no network, no model) so
the demo is stable and offline. Only ``power.switch(state=true/false)`` on the
simulated "cuarto" lamp can reach Runtime. Nothing here touches hardware,
cloud, API, or Dashboard. The decision surface remains non-executing; only the
ExecutionGate may forward a validated candidate to Runtime.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jarvis_core.ai.context import SafeContextBuilder  # noqa: E402
from jarvis_core.ai.execution_gate import ExecutionGate  # noqa: E402
from jarvis_core.ai.understanding_decision import decide_understanding  # noqa: E402
from jarvis_core.ai.understanding_diagnostic import describe_decision  # noqa: E402
from jarvis_core.bootstrap import build_http_runtime  # noqa: E402
from jarvis_core.devices import Device, DeviceCapability  # noqa: E402
from jarvis_core.drivers import SimulatedDriver  # noqa: E402

POWER_ON_TERMS = ("enciende", "prende", "encender", "turn on", "switch on")
POWER_OFF_TERMS = ("apaga", "apagar", "turn off", "switch off")


def run_ai_execution_gate(request: str, *, show_canonical: bool = False) -> dict[str, object]:
    request = request.strip()
    if not request:
        raise ValueError("--request is required")
    runtime = demo_runtime()
    context = SafeContextBuilder().build(request, runtime.context.device_registry)
    decision = decide_understanding(
        DemoUnderstandingProvider(),
        context,
        provider_id="demo-understanding-provider",
        model_id="deterministic-v1",
    )
    result = ExecutionGate(runtime).execute(decision)

    runtime_payload = None
    if result.executed:
        runtime_payload = {
            "success": result.runtime_result.success,
            "message": result.runtime_result.message,
            "error": result.runtime_result.error,
        }
    return {
        "provider": "demo-understanding-provider",
        "model": "deterministic-v1",
        "fixture_set": "ai-execution-gate-local-fixture",
        "execution": {
            "runtime": result.executed,
            "drivers": result.executed,
            "hardware": False,
            "cloud": False,
        },
        "decision": describe_decision(decision, show_canonical=show_canonical),
        "gate": {
            "executed": result.executed,
            "device_id": result.device_id,
            "capability": result.capability,
            "arguments": result.arguments,
            "reason": result.reason,
            "runtime": runtime_payload,
        },
        "device_room": context.devices[0].room if context.devices else None,
    }


class DemoUnderstandingProvider:
    """Keyword-based deterministic understanding extraction (offline demo)."""

    def extract_understanding(self, context):
        lowered = context.user_request.casefold()
        state = _detect_state(lowered)
        return {
            "intent": "mutate",
            "referenced_device_text": "luz",
            "capability_hint": "power.switch" if state else None,
            "operation_hint": "apply",
            "raw_arguments": [["state", state]] if state else [],
        }


def _detect_state(lowered):
    if any(term in lowered for term in POWER_ON_TERMS):
        return "true"
    if any(term in lowered for term in POWER_OFF_TERMS):
        return "false"
    return None


def demo_runtime():
    return build_http_runtime(DemoActionDriver(), devices=[demo_lamp()])


class DemoActionDriver(SimulatedDriver):
    def apply(self, device, capability_name, parameters):
        result = super().apply(device, capability_name, parameters)
        if result.success:
            result.observations["power"] = parameters.get("state") == "true"
        return result


def demo_lamp():
    return Device(
        id="lamp_1",
        name="Lamp",
        type="light",
        capabilities=[
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"type": "string", "required": True}},
            ),
            DeviceCapability(name="status.read", kind="reading", parameters={}),
        ],
        metadata={"room": "cuarto"},
    )


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        payload = run_ai_execution_gate(args.request, show_canonical=args.show_canonical)
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print("decision:")
    print(format_gate_text_payload(payload))
    return 0


def format_gate_text_payload(payload: dict[str, object]) -> str:
    """Render the gate CLI payload without re-running the execution."""
    decision = payload.get("decision")
    gate = payload.get("gate")
    if not isinstance(decision, dict) or not isinstance(gate, dict):
        return "gate result unavailable"
    lines = [f"status: {decision.get('status') or 'null'}"]
    safe_summary = decision.get("safe_summary")
    if safe_summary:
        lines.append(f"safe_summary: {safe_summary}")
    clarification = decision.get("clarification")
    if isinstance(clarification, dict) and clarification.get("question"):
        lines.append(
            "clarification: "
            f"{clarification['question']} (reason: {clarification.get('reason_code')})"
        )
    if gate.get("executed"):
        lines.append("gate_executed: true")
        lines.append(f"device_id: {gate.get('device_id')}")
        lines.append(f"capability: {gate.get('capability')}")
        lines.append(f"arguments: {gate.get('arguments')}")
        runtime = gate.get("runtime") or {}
        lines.append(f"runtime_success: {str(bool(runtime.get('success'))).lower()}")
        lines.append(f"runtime_message: {runtime.get('message')}")
        if runtime.get("error"):
            lines.append(f"runtime_error: {runtime.get('error')}")
    else:
        lines.append("gate_executed: false")
        lines.append(f"blocked_reason: {gate.get('reason')}")
    return "\n".join(lines)


def _parse_args(argv=None):
    parser = build_argument_parser()
    return parser.parse_args(argv)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe local understanding execution demo (simulated runtime)",
        epilog=(
            "Runs one deterministic understanding decision through the existing "
            "ExecutionGate and a simulated in-memory Runtime/Driver. Only "
            "power.switch(state=true/false) on the simulated 'cuarto' lamp can be "
            "executed; hardware, cloud, API and Dashboard are never touched."
        ),
    )
    parser.add_argument("--request", required=True, metavar="TEXT", help="User request to understand and gate")
    parser.add_argument("--show-canonical", action="store_true", help="Show the canonical command text explicitly")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())