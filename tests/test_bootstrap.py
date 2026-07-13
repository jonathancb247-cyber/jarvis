import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from jarvis_core.bootstrap import (
    build_http_runtime,
    build_runtime,
    build_runtime_from_config,
    build_runtime_from_profile,
)
from jarvis_core.configuration import RuntimeConfigurationLoader
from jarvis_core.devices import Device, DeviceCapability
from jarvis_core.http_driver import (
    HttpDeviceBinding,
    HttpDeviceBindingStore,
    HttpDeviceDriver,
    HttpJsonResponse,
)
from jarvis_core.state_store import STATE_STORE_CORRUPT, StateStoreError
from jarvis_core.state_store import JsonDeviceStateStore, STATE_SAVE_FAILED


class FakeHttpTransport:
    def __init__(self):
        self.calls = []

    def post_json(self, url, payload, timeout_seconds, max_response_bytes):
        self.calls.append((url, payload, timeout_seconds, max_response_bytes))
        return HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": True}},
        )


class BootstrapTests(unittest.TestCase):
    def make_http_runtime(self):
        store = HttpDeviceBindingStore()
        store.register(HttpDeviceBinding("lamp_1", "http://localhost:8000"))
        transport = FakeHttpTransport()
        driver = HttpDeviceDriver(store, transport=transport)
        device = Device(
            id="lamp_1",
            name="Lamp",
            type="light",
            capabilities=[
                DeviceCapability(
                    name="power.switch",
                    kind="action",
                    parameters={"state": {"type": "string", "required": True}},
                ),
                DeviceCapability(name="status.read", kind="reading"),
            ],
        )
        return build_http_runtime(driver, devices=[device]), transport

    def test_default_runtime_has_no_demo_device_and_uses_no_http_network(self):
        runtime = build_runtime()

        result = runtime.handle_adapter_input("device list")

        self.assertTrue(result.success)
        self.assertEqual({"count": 0, "devices": []}, result.data)

    def test_default_runtime_still_handles_time(self):
        runtime = build_runtime()

        result = runtime.handle_adapter_input("what time is it?")

        self.assertTrue(result.success)
        self.assertTrue(result.message.startswith("The current time is "))

    def test_http_runtime_vertical_slice_uses_fake_transport(self):
        runtime, transport = self.make_http_runtime()

        apply_result = runtime.handle_adapter_input(
            "device apply lamp_1 power.switch state=true",
            source="cli",
        )
        read_result = runtime.handle_adapter_input(
            "device read lamp_1 status.read",
            source="cli",
        )
        state_result = runtime.handle_adapter_input("device state lamp_1", source="cli")

        self.assertTrue(apply_result.success)
        self.assertEqual("Device action completed.", apply_result.message)
        self.assertTrue(read_result.success)
        self.assertTrue(state_result.success)
        self.assertEqual({"power": True}, state_result.data["state"]["properties"])
        self.assertEqual(2, len(transport.calls))

    def test_build_http_runtime_rejects_invalid_driver(self):
        with self.assertRaises(TypeError):
            build_http_runtime(object())

    def test_build_runtime_from_profile_uses_fake_http_transport(self):
        profile = RuntimeConfigurationLoader().load("profiles/http-lab.example.json")
        transport = FakeHttpTransport()
        runtime = build_runtime_from_profile(profile, http_transport=transport)

        apply_result = runtime.handle_adapter_input(
            "device apply lamp_1 power.switch state=true",
            source="cli",
        )
        read_result = runtime.handle_adapter_input(
            "device read lamp_1 status.read",
            source="cli",
        )
        state_result = runtime.handle_adapter_input("device state lamp_1", source="cli")
        list_result = runtime.handle_adapter_input("device list", source="cli")

        self.assertTrue(apply_result.success)
        self.assertTrue(read_result.success)
        self.assertTrue(state_result.success)
        self.assertEqual(state_result.data["state"]["properties"], {"power": True})
        self.assertEqual(list_result.data["count"], 1)
        self.assertEqual(transport.calls[0][0], "http://192.168.1.50/device/apply")
        self.assertEqual(transport.calls[1][0], "http://192.168.1.50/device/read")

    def test_build_runtime_from_config_restores_state_as_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = root / "state" / "http-lab.state.json"
            state_path.parent.mkdir()
            state_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "states": {
                            "lamp_1": {
                                "status": "known",
                                "properties": {"power": True},
                                "updated_at": "2026-07-13T12:00:00+00:00",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            config_path = write_profile(root, "state/http-lab.state.json")

            runtime = build_runtime_from_config(
                config_path,
                http_transport=FakeHttpTransport(),
            )

            state_result = runtime.handle_adapter_input("device state lamp_1")
            self.assertEqual(state_result.data["state"]["status"], "stale")
            self.assertEqual(state_result.data["state"]["properties"], {"power": True})

    def test_build_runtime_from_config_missing_state_file_starts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = write_profile(root, "state/http-lab.state.json")

            runtime = build_runtime_from_config(
                config_path,
                http_transport=FakeHttpTransport(),
            )

            state_result = runtime.handle_adapter_input("device state lamp_1")
            self.assertEqual(state_result.data["state"]["status"], "unknown")

    def test_build_runtime_from_config_corrupt_state_fails_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = root / "state" / "http-lab.state.json"
            state_path.parent.mkdir()
            state_path.write_text("{", encoding="utf-8")
            config_path = write_profile(root, "state/http-lab.state.json")

            with self.assertRaises(StateStoreError) as context:
                build_runtime_from_config(config_path, http_transport=FakeHttpTransport())

            self.assertEqual(context.exception.code, STATE_STORE_CORRUPT)

    def test_state_update_saves_snapshot_and_restart_restores_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = write_profile(root, "state/http-lab.state.json")

            runtime = build_runtime_from_config(
                config_path,
                http_transport=FakeHttpTransport(),
            )
            apply_result = runtime.handle_adapter_input(
                "device apply lamp_1 power.switch state=true",
                source="cli",
            )
            self.assertTrue(apply_result.success)

            state_path = root / "state" / "http-lab.state.json"
            self.assertTrue(state_path.exists())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["states"]["lamp_1"]["properties"], {"power": True})
            self.assertNotIn("http_bindings", saved)
            self.assertNotIn("http://192.168.1.50", state_path.read_text(encoding="utf-8"))

            restarted = build_runtime_from_config(
                config_path,
                http_transport=FakeHttpTransport(),
            )
            state_result = restarted.handle_adapter_input("device state lamp_1")
            self.assertEqual(state_result.data["state"]["status"], "stale")
            self.assertEqual(state_result.data["state"]["properties"], {"power": True})

    def test_failed_driver_operation_does_not_create_snapshot(self):
        class FailingTransport:
            def post_json(self, url, payload, timeout_seconds, max_response_bytes):
                raise TimeoutError("timeout")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = write_profile(root, "state/http-lab.state.json")
            runtime = build_runtime_from_config(
                config_path,
                http_transport=FailingTransport(),
            )

            result = runtime.handle_adapter_input("device read lamp_1 status.read")

            self.assertFalse(result.success)
            self.assertFalse((root / "state" / "http-lab.state.json").exists())

    def test_save_failure_does_not_turn_physical_success_into_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = write_profile(root, "state/http-lab.state.json")
            runtime = build_runtime_from_config(
                config_path,
                http_transport=FakeHttpTransport(),
            )

            with patch.object(
                JsonDeviceStateStore,
                "save",
                side_effect=StateStoreError(STATE_SAVE_FAILED),
            ):
                result = runtime.handle_adapter_input(
                    "device apply lamp_1 power.switch state=true",
                    source="cli",
                )

            self.assertTrue(result.success)
            self.assertEqual(result.message, "Device action completed.")

    def test_final_shutdown_saves_current_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = write_profile(root, "state/http-lab.state.json")
            runtime = build_runtime_from_config(
                config_path,
                http_transport=FakeHttpTransport(),
            )

            runtime.shutdown()

            payload = json.loads(
                (root / "state" / "http-lab.state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["states"]["lamp_1"]["status"], "unknown")


def write_profile(root, state_store_path):
    path = root / "profile.json"
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
                "runtime_options": {"state_store_path": state_store_path},
            }
        ),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
