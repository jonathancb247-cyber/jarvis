"""Run the local Wear OS presence validation receiver."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jarvis_core.cognitive import CognitiveBenchmarkRunner
from jarvis_core.cognitive.models import AttentionAction, JudgmentAction, ScenarioInput
from jarvis_core.wearable import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_STALE_TIMEOUT_SECONDS,
    DEFAULT_WEARABLE_ID,
    WearablePresenceReceiver,
    wearable_projection_to_signal,
)
from jarvis_core.wearable.http_receiver import PRESENCE_PATH, STATUS_PATH, build_presence_http_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the validation-only Wear OS presence receiver.")
    parser.add_argument("--host", default="127.0.0.1", help="Explicit local bind host.")
    parser.add_argument("--port", type=int, default=8766, help="Local validation receiver port.")
    parser.add_argument("--wearable-id", default=DEFAULT_WEARABLE_ID)
    parser.add_argument("--stale-timeout-seconds", type=float, default=DEFAULT_STALE_TIMEOUT_SECONDS)
    parser.add_argument("--once", action="store_true", help="Print the current unknown diagnostic snapshot and exit.")
    args = parser.parse_args(argv)

    receiver = WearablePresenceReceiver(
        expected_wearable_id=args.wearable_id,
        stale_timeout_seconds=args.stale_timeout_seconds,
    )
    if args.once:
        print(_diagnostic_payload(receiver), end="")
        return 0

    server = build_presence_http_server(host=args.host, port=args.port, receiver=receiver)
    print("JarvisOS Wearable Presence Receiver")
    print(f"bind: http://{args.host}:{args.port}")
    print(f"presence_path: {PRESENCE_PATH}")
    print(f"status_path: {STATUS_PATH}")
    print(f"wearable_id: {args.wearable_id}")
    print(f"heartbeat_interval_seconds: {DEFAULT_HEARTBEAT_INTERVAL_SECONDS:.1f}")
    print(f"stale_timeout_seconds: {args.stale_timeout_seconds:.1f}")
    print("validation_only: true")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nreceiver_stopped")
    finally:
        server.server_close()
    return 0


def _diagnostic_payload(receiver: WearablePresenceReceiver) -> str:
    projection = receiver.projection()
    signal = wearable_projection_to_signal(projection)
    connected = signal.kind == "watch_connected"
    report = CognitiveBenchmarkRunner(
        (
            ScenarioInput(
                scenario_id="wearable_presence_probe",
                name="Wearable Presence Probe",
                signals=(signal,),
                expected_judgment=JudgmentAction.SUGGEST if connected else JudgmentAction.CLARIFY,
                expected_attention=AttentionAction.SURFACE,
            ),
        )
    ).run()
    payload = {
        "projection": {
            "wearable_id": projection.wearable_id,
            "connection_state": projection.connection_state.value,
            "capability_status": projection.capability_status.value,
            "freshness": projection.freshness.value,
            "confidence": projection.confidence.value,
            "safe_explanation": projection.safe_explanation,
        },
        "signal": {
            "kind": signal.kind,
            "freshness": signal.freshness.value,
            "confidence": signal.confidence.value,
            "safe_explanation": signal.safe_explanation,
        },
        "diagnostic_report": report.as_dict(),
    }
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
