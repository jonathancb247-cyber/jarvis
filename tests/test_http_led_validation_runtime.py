import importlib.util
from pathlib import Path
import unittest

from jarvis_core.http_driver import HttpJsonResponse


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "run_http_led_validation.py"
)


def load_validation_module():
    spec = importlib.util.spec_from_file_location(
        "run_http_led_validation",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeLedTransport:
    def __init__(self):
        self.power = False
        self.calls = []

    def post_json(self, url, payload, timeout_seconds, max_response_bytes):
        self.calls.append(
            {
                "url": url,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        if url.endswith("/device/apply"):
            state = payload["parameters"]["state"]
            self.power = state == "true"
        return HttpJsonResponse(
            200,
            "application/json",
            {
                "success": True,
                "observations": {"power": self.power},
            },
        )


class HttpLedValidationRuntimeTests(unittest.TestCase):
    def test_validation_runtime_controls_fake_led_through_jarvis_pipeline(self):
        module = load_validation_module()
        transport = FakeLedTransport()
        runtime = module.build_http_led_validation_runtime(
            base_url="http://localhost",
            transport=transport,
        )

        on_result = runtime.handle_adapter_input(
            "device apply lamp_1 power.switch state=true"
        )
        read_on = runtime.handle_adapter_input("device read lamp_1 status.read")
        state_on = runtime.handle_adapter_input("device state lamp_1")
        off_result = runtime.handle_adapter_input(
            "device apply lamp_1 power.switch state=false"
        )
        read_off = runtime.handle_adapter_input("device read lamp_1 status.read")
        state_off = runtime.handle_adapter_input("device state lamp_1")

        self.assertTrue(on_result.success)
        self.assertTrue(read_on.success)
        self.assertTrue(state_on.success)
        self.assertEqual({"power": True}, state_on.data["state"]["properties"])
        self.assertTrue(off_result.success)
        self.assertTrue(read_off.success)
        self.assertTrue(state_off.success)
        self.assertEqual({"power": False}, state_off.data["state"]["properties"])
        self.assertEqual(4, len(transport.calls))
        self.assertTrue(all(call["url"].startswith("http://localhost") for call in transport.calls))

    def test_validation_runtime_has_no_demo_beyond_explicit_lamp(self):
        module = load_validation_module()
        runtime = module.build_http_led_validation_runtime(
            base_url="http://localhost",
            transport=FakeLedTransport(),
        )

        result = runtime.handle_adapter_input("device list")

        self.assertTrue(result.success)
        self.assertEqual(1, result.data["count"])
        self.assertEqual("lamp_1", result.data["devices"][0]["id"])


if __name__ == "__main__":
    unittest.main()
