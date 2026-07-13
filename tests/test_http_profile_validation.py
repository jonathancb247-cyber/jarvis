import json
import tempfile
from pathlib import Path
import unittest

from jarvis_core.bootstrap import build_runtime, build_runtime_from_config
from jarvis_core.http_driver import HttpJsonResponse


class ScenarioHttpTransport:
    def __init__(self, responses):
        self.responses = list(responses)
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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class HttpProfileValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.config_path = write_local_profile(self.root)
        self.state_path = self.root / "state" / "http-lab.state.json"

    def test_profile_based_runtime_startup_loads_device_without_network(self):
        transport = ScenarioHttpTransport([])

        runtime = build_runtime_from_config(self.config_path, http_transport=transport)
        list_result = runtime.handle_adapter_input("device list")
        info_result = runtime.handle_adapter_input("device info lamp_1")
        capabilities_result = runtime.handle_adapter_input("device capabilities lamp_1")
        state_result = runtime.handle_adapter_input("device state lamp_1")

        self.assertTrue(list_result.success)
        self.assertEqual(list_result.data["devices"][0]["id"], "lamp_1")
        self.assertTrue(info_result.success)
        self.assertTrue(capabilities_result.success)
        self.assertEqual(
            [item["name"] for item in capabilities_result.data["formal"]],
            ["power.switch", "status.read"],
        )
        self.assertEqual(state_result.data["state"]["status"], "unknown")
        self.assertEqual(transport.calls, [])

    def test_profile_vertical_slice_restarts_stale_then_read_returns_known(self):
        first_transport = ScenarioHttpTransport(
            [
                success_response(power=True),
                success_response(power=True),
            ]
        )
        runtime = build_runtime_from_config(
            self.config_path,
            http_transport=first_transport,
        )

        apply_result = runtime.handle_adapter_input(
            "device apply lamp_1 power.switch state=true",
        )
        read_result = runtime.handle_adapter_input("device read lamp_1 status.read")
        state_result = runtime.handle_adapter_input("device state lamp_1")
        runtime.shutdown()

        self.assertTrue(apply_result.success)
        self.assertTrue(read_result.success)
        self.assertEqual(state_result.data["state"]["status"], "known")
        self.assertEqual(state_result.data["state"]["properties"], {"power": True})
        self.assertTrue(self.state_path.exists())

        restarted_transport = ScenarioHttpTransport([success_response(power=True)])
        restarted = build_runtime_from_config(
            self.config_path,
            http_transport=restarted_transport,
        )

        stale_result = restarted.handle_adapter_input("device state lamp_1")
        read_after_restart = restarted.handle_adapter_input("device read lamp_1 status.read")
        known_result = restarted.handle_adapter_input("device state lamp_1")

        self.assertEqual(stale_result.data["state"]["status"], "stale")
        self.assertEqual(stale_result.data["state"]["properties"], {"power": True})
        self.assertTrue(read_after_restart.success)
        self.assertEqual(known_result.data["state"]["status"], "known")
        self.assertEqual(known_result.data["state"]["properties"], {"power": True})
        self.assertEqual(len(restarted_transport.calls), 1)

    def test_subsequent_snapshot_reflects_latest_saved_properties(self):
        runtime = build_runtime_from_config(
            self.config_path,
            http_transport=ScenarioHttpTransport(
                [
                    success_response(power=True),
                    success_response(power=False),
                ]
            ),
        )

        runtime.handle_adapter_input("device apply lamp_1 power.switch state=true")
        runtime.handle_adapter_input("device apply lamp_1 power.switch state=false")
        runtime.shutdown()

        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["states"]["lamp_1"]["properties"], {"power": False})

        restarted = build_runtime_from_config(
            self.config_path,
            http_transport=ScenarioHttpTransport([]),
        )
        state_result = restarted.handle_adapter_input("device state lamp_1")
        self.assertEqual(state_result.data["state"]["status"], "stale")
        self.assertEqual(state_result.data["state"]["properties"], {"power": False})

    def test_connection_failure_does_not_persist_technical_data_or_overwrite_state(self):
        runtime = build_runtime_from_config(
            self.config_path,
            http_transport=ScenarioHttpTransport([success_response(power=True)]),
        )
        runtime.handle_adapter_input("device read lamp_1 status.read")
        before = json.loads(self.state_path.read_text(encoding="utf-8"))

        failing = build_runtime_from_config(
            self.config_path,
            http_transport=ScenarioHttpTransport([TimeoutError("http://192.168.1.50")]),
        )
        result = failing.handle_adapter_input("device read lamp_1 status.read")
        after = json.loads(self.state_path.read_text(encoding="utf-8"))
        state_result = failing.handle_adapter_input("device state lamp_1")

        self.assertFalse(result.success)
        self.assertEqual(result.error, "device_execution_failed")
        self.assertNotIn("192.168.1.50", str(result.data))
        self.assertNotIn("TimeoutError", str(result.data))
        self.assertEqual(after, before)
        self.assertEqual(state_result.data["state"]["status"], "stale")
        self.assertEqual(state_result.data["state"]["properties"], {"power": True})

    def test_default_runtime_remains_empty_offline_and_without_state_store(self):
        runtime = build_runtime()

        list_result = runtime.handle_adapter_input("device list")
        runtime.shutdown()

        self.assertEqual(list_result.data, {"count": 0, "devices": []})
        self.assertFalse(self.state_path.exists())


def success_response(power):
    return HttpJsonResponse(
        200,
        "application/json",
        {"success": True, "observations": {"power": power}, "error": None},
    )


def write_local_profile(root):
    profiles_dir = root / "profiles"
    profiles_dir.mkdir()
    path = profiles_dir / "http-lab.local.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile": "http-lab",
                "devices": [
                    {
                        "id": "lamp_1",
                        "name": "ESP32 LED",
                        "type": "light",
                        "capabilities": [
                            {
                                "name": "power.switch",
                                "kind": "action",
                                "parameters": {
                                    "state": {"type": "string", "required": True}
                                },
                                "constraints": {},
                                "availability_policy": {},
                            },
                            {
                                "name": "status.read",
                                "kind": "reading",
                                "parameters": {},
                                "constraints": {},
                                "availability_policy": {},
                            },
                        ],
                        "metadata": {},
                    }
                ],
                "http_bindings": [
                    {
                        "device_id": "lamp_1",
                        "base_url": "http://192.168.1.50",
                        "timeout_seconds": 2.0,
                        "read_path": "/device/read",
                        "apply_path": "/device/apply",
                    }
                ],
                "runtime_options": {
                    "state_store_path": "../state/http-lab.state.json"
                },
            }
        ),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
