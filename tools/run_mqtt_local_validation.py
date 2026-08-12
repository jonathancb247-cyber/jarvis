"""Manual local Mosquitto validation runner for Phase 12.3."""

import argparse
import json
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.configuration import RuntimeConfigurationLoader
from jarvis_core.mqtt_paho import PahoMQTTClient


COMMANDS = [
    "device state lamp_1",
    "device read lamp_1 status.read",
    "device apply lamp_1 power.switch state=true",
    "device apply lamp_1 power.switch state=false",
]


def main(argv=None):
    args = _parse_args(argv)
    profile = RuntimeConfigurationLoader().load(args.config)
    response_topics = tuple(binding.response_topic for binding in profile.mqtt_bindings)
    mqtt_client = PahoMQTTClient(
        host=args.broker_host,
        port=args.broker_port,
        response_topics=response_topics,
        connect_timeout_seconds=args.connect_timeout,
    )
    runtime = build_runtime_from_config(args.config, mqtt_client=mqtt_client)
    try:
        results = []
        for command in COMMANDS:
            started = time.monotonic()
            result = runtime.handle_adapter_input(command, source="mqtt-validation")
            latency_ms = int((time.monotonic() - started) * 1000)
            results.append(
                {
                    "command": command,
                    "success": result.success,
                    "error": result.error,
                    "latency_ms": latency_ms,
                    "state_status": _state_status(result.data),
                    "properties": _properties(result.data),
                }
            )
        print(json.dumps(results, sort_keys=True))
        return 0 if all(item["success"] for item in results[1:]) else 1
    finally:
        runtime.shutdown()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python tools/run_mqtt_local_validation.py",
        description="Run JarvisOS against a loopback Mosquitto broker and simulated MQTT lamp.",
    )
    parser.add_argument(
        "--config",
        default="profiles/mqtt-lab.example.json",
        help="Path to the local MQTT validation profile.",
    )
    parser.add_argument("--broker-host", default="127.0.0.1")
    parser.add_argument("--broker-port", type=int, default=1883)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    return parser.parse_args(argv)


def _state_status(data):
    state = data.get("state") if isinstance(data, dict) else None
    if isinstance(state, dict):
        return state.get("status")
    return None


def _properties(data):
    state = data.get("state") if isinstance(data, dict) else None
    if isinstance(state, dict):
        return state.get("properties")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
