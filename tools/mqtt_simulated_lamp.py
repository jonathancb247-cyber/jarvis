"""Local validation-only MQTT lamp responder.

This tool is not product architecture. It exists only to validate JarvisOS
MQTT request/response behavior through a real local broker.
"""

import argparse
import json
import signal
import threading

import paho.mqtt.client as mqtt


REQUEST_FIELDS = {"request_id", "device_id", "capability", "operation", "parameters"}
DEFAULT_REQUEST_TOPIC = "jarvis/lab/lamp_1/request"
DEFAULT_RESPONSE_TOPIC = "jarvis/lab/lamp_1/response"


class SimulatedLamp:
    def __init__(self, response_topic, initial_power=False):
        self.response_topic = response_topic
        self.power = bool(initial_power)
        self.lock = threading.Lock()

    def handle(self, payload):
        try:
            request = json.loads(payload.decode("utf-8"))
        except Exception:
            return None
        if not isinstance(request, dict) or set(request.keys()) != REQUEST_FIELDS:
            return None
        request_id = request["request_id"]
        capability = request["capability"]
        operation = request["operation"]
        parameters = request["parameters"]
        if not isinstance(request_id, str) or not request_id:
            return None
        if request.get("device_id") != "lamp_1":
            return _response(request_id, False, {}, "invalid_device")
        if not isinstance(parameters, dict):
            return _response(request_id, False, {}, "invalid_parameters")
        with self.lock:
            if operation == "read" and capability == "status.read":
                return _response(request_id, True, {"power": self.power}, None)
            if operation == "apply" and capability == "power.switch":
                state = parameters.get("state")
                if state == "true":
                    self.power = True
                    return _response(request_id, True, {"power": True}, None)
                if state == "false":
                    self.power = False
                    return _response(request_id, True, {"power": False}, None)
                return _response(request_id, False, {}, "invalid_parameters")
        return _response(request_id, False, {}, "operation_not_supported")


def main(argv=None):
    args = _parse_args(argv)
    stop_event = threading.Event()
    lamp = SimulatedLamp(args.response_topic, initial_power=args.initial_power)
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=args.client_id,
    )

    def on_connect(client, userdata, flags, reason_code, properties=None):
        if _is_success(reason_code):
            client.subscribe(args.request_topic, qos=0)

    def on_message(client, userdata, message):
        response = lamp.handle(message.payload)
        if response is not None:
            client.publish(args.response_topic, response, qos=0, retain=False)

    def handle_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()
    try:
        print("MQTT simulated lamp ready.")
        stop_event.wait()
    finally:
        client.disconnect()
        client.loop_stop()
        print("MQTT simulated lamp stopped.")
    return 0


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python tools/mqtt_simulated_lamp.py",
        description="Run a local validation-only MQTT lamp responder.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--request-topic", default=DEFAULT_REQUEST_TOPIC)
    parser.add_argument("--response-topic", default=DEFAULT_RESPONSE_TOPIC)
    parser.add_argument("--client-id", default="jarvisos-simulated-lamp")
    parser.add_argument("--initial-power", action="store_true")
    return parser.parse_args(argv)


def _response(request_id, ok, semantic, error):
    return json.dumps(
        {
            "request_id": request_id,
            "ok": ok,
            "semantic": semantic,
            "error": error,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_success(reason_code):
    if reason_code == 0:
        return True
    value = getattr(reason_code, "value", None)
    if value == 0:
        return True
    return str(reason_code).lower() in {"success", "0"}


if __name__ == "__main__":
    raise SystemExit(main())
