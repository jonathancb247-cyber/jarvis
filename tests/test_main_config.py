import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from jarvis_core import __main__ as jarvis_main


class MainConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_main_without_args_uses_default_runtime(self):
        captured = {}

        with patch.object(jarvis_main, "run_cli", _capture_runtime(captured)):
            exit_code = jarvis_main.main([])

        self.assertEqual(exit_code, 0)
        result = captured["runtime"].handle_adapter_input("device list")
        self.assertTrue(result.success)
        self.assertEqual(result.data, {"count": 0, "devices": []})

    def test_main_with_valid_config_starts_configured_runtime(self):
        path = self.write_profile()
        captured = {}

        with patch.object(jarvis_main, "run_cli", _capture_runtime(captured)):
            exit_code = jarvis_main.main(["--config", str(path)])

        self.assertEqual(exit_code, 0)
        result = captured["runtime"].handle_adapter_input("device list")
        self.assertTrue(result.success)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["devices"][0]["id"], "lamp_1")

    def test_main_with_missing_config_returns_safe_startup_error(self):
        output = []

        with patch("builtins.print", _capture_print(output)):
            exit_code = jarvis_main.main(["--config", str(self.root / "missing.json")])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, ["Configuration file was not found."])

    def test_main_with_invalid_config_returns_safe_startup_error(self):
        path = self.root / "invalid.json"
        path.write_text("{", encoding="utf-8")
        output = []

        with patch("builtins.print", _capture_print(output)):
            exit_code = jarvis_main.main(["--config", str(path)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, ["Configuration is invalid."])
        self.assertNotIn(str(path), str(output))
        self.assertNotIn("Traceback", str(output))

    def test_main_with_corrupt_state_store_returns_safe_startup_error(self):
        state_path = self.root / "state" / "http-lab.state.json"
        state_path.parent.mkdir()
        state_path.write_text("{", encoding="utf-8")
        path = self.write_profile(runtime_options={"state_store_path": "state/http-lab.state.json"})
        output = []

        with patch("builtins.print", _capture_print(output)):
            exit_code = jarvis_main.main(["--config", str(path)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(output, ["State store is corrupt."])
        self.assertNotIn(str(state_path), str(output))
        self.assertNotIn("Traceback", str(output))

    def test_profile_argument_is_not_supported(self):
        with patch("sys.stderr", new_callable=_StringSink):
            with self.assertRaises(SystemExit):
                jarvis_main.main(["--profile", "http-lab"])

    def write_profile(self, runtime_options=None):
        path = self.root / "profile.json"
        payload = valid_profile()
        if runtime_options is not None:
            payload["runtime_options"] = runtime_options
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


def valid_profile():
    return {
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
        "runtime_options": {},
    }


def _capture_runtime(captured):
    def capture(runtime):
        captured["runtime"] = runtime

    return capture


def _capture_print(output):
    def write(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        output.append(sep.join(str(arg) for arg in args))

    return write


class _StringSink:
    def write(self, value):
        return len(value)

    def flush(self):
        return None


if __name__ == "__main__":
    unittest.main()
