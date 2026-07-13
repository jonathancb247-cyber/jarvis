import json
import tempfile
from pathlib import Path
import unittest

from jarvis_core.configuration import (
    CONFIG_INVALID,
    CONFIG_NOT_FOUND,
    DUPLICATE_DEVICE,
    INVALID_BINDING,
    INVALID_CAPABILITY,
    ORPHAN_BINDING,
    SCHEMA_VERSION_UNSUPPORTED,
    ConfigurationError,
    RuntimeConfigurationLoader,
    RuntimeProfile,
    build_devices,
    build_http_bindings,
)
from jarvis_core.devices import DeviceCapability


class RuntimeConfigurationLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_load_valid_profile(self):
        path = self.write_profile(valid_profile())

        profile = RuntimeConfigurationLoader().load(path)

        self.assertIsInstance(profile, RuntimeProfile)
        self.assertEqual(profile.schema_version, 1)
        self.assertEqual(profile.name, "http-lab")
        self.assertEqual(len(profile.devices), 1)
        self.assertEqual(len(profile.http_bindings), 1)
        self.assertEqual(profile.runtime_options, {})

    def test_config_not_found(self):
        with self.assertConfigError(CONFIG_NOT_FOUND):
            RuntimeConfigurationLoader().load(self.root / "missing.json")

    def test_path_is_directory(self):
        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(self.root)

    def test_oversized_config(self):
        path = self.root / "large.json"
        path.write_text(" " * 70000, encoding="utf-8")

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_utf8(self):
        path = self.root / "invalid.json"
        path.write_bytes(b"\xff")

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_json(self):
        path = self.root / "invalid.json"
        path.write_text("{", encoding="utf-8")

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_root_must_be_object(self):
        path = self.write_json([])

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_missing_root_field(self):
        payload = valid_profile()
        del payload["devices"]
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_unknown_root_field(self):
        payload = valid_profile()
        payload["unexpected"] = True
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_unsupported_schema(self):
        payload = valid_profile()
        payload["schema_version"] = 2
        path = self.write_profile(payload)

        with self.assertConfigError(SCHEMA_VERSION_UNSUPPORTED):
            RuntimeConfigurationLoader().load(path)

    def test_empty_profile_name(self):
        payload = valid_profile()
        payload["profile"] = ""
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_devices_must_be_list(self):
        payload = valid_profile()
        payload["devices"] = {}
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_bindings_must_be_list(self):
        payload = valid_profile()
        payload["http_bindings"] = {}
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_runtime_options_must_be_empty_object(self):
        payload = valid_profile()
        payload["runtime_options"] = {"state_store_path": "state.json"}
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_duplicate_device(self):
        payload = valid_profile()
        payload["devices"].append(payload["devices"][0].copy())
        path = self.write_profile(payload)

        with self.assertConfigError(DUPLICATE_DEVICE):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_device_id(self):
        payload = valid_profile()
        payload["devices"][0]["id"] = ""
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_device_name(self):
        payload = valid_profile()
        payload["devices"][0]["name"] = ""
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_device_type(self):
        payload = valid_profile()
        payload["devices"][0]["type"] = ""
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_capabilities_must_be_list(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"] = {}
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_metadata_must_be_object(self):
        payload = valid_profile()
        payload["devices"][0]["metadata"] = []
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_non_empty_metadata_rejected(self):
        payload = valid_profile()
        payload["devices"][0]["metadata"] = {"room": "lab"}
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_device_state_in_config_rejected(self):
        payload = valid_profile()
        payload["devices"][0]["state"] = {"status": "known"}
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_unknown_device_field_rejected(self):
        payload = valid_profile()
        payload["devices"][0]["url"] = "http://localhost"
        path = self.write_profile(payload)

        with self.assertConfigError(CONFIG_INVALID):
            RuntimeConfigurationLoader().load(path)

    def test_valid_action_and_reading_capabilities(self):
        path = self.write_profile(valid_profile())

        profile = RuntimeConfigurationLoader().load(path)

        kinds = [capability.kind for capability in profile.devices[0].capabilities]
        self.assertEqual(kinds, ["action", "reading"])

    def test_invalid_capability_kind(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"][0]["kind"] = "driver"
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_CAPABILITY):
            RuntimeConfigurationLoader().load(path)

    def test_duplicate_capability(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"][1]["name"] = "power.switch"
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_CAPABILITY):
            RuntimeConfigurationLoader().load(path)

    def test_legacy_capability_string_rejected(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"] = ["power.switch"]
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_CAPABILITY):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_parameters(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"][0]["parameters"] = []
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_CAPABILITY):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_parameter_descriptor(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"][0]["parameters"]["state"] = []
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_CAPABILITY):
            RuntimeConfigurationLoader().load(path)

    def test_unknown_parameter_descriptor_field_rejected(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"][0]["parameters"]["state"]["url"] = "x"
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_CAPABILITY):
            RuntimeConfigurationLoader().load(path)

    def test_required_parameter_must_be_bool(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"][0]["parameters"]["state"][
            "required"
        ] = "yes"
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_CAPABILITY):
            RuntimeConfigurationLoader().load(path)

    def test_unknown_capability_field_rejected(self):
        payload = valid_profile()
        payload["devices"][0]["capabilities"][0]["http_path"] = "/device/apply"
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_CAPABILITY):
            RuntimeConfigurationLoader().load(path)

    def test_valid_binding(self):
        path = self.write_profile(valid_profile())

        profile = RuntimeConfigurationLoader().load(path)

        self.assertEqual(profile.http_bindings[0].device_id, "lamp_1")
        self.assertEqual(profile.http_bindings[0].base_url, "http://192.168.1.50")

    def test_duplicate_binding(self):
        payload = valid_profile()
        payload["http_bindings"].append(payload["http_bindings"][0].copy())
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_BINDING):
            RuntimeConfigurationLoader().load(path)

    def test_orphan_binding(self):
        payload = valid_profile()
        payload["http_bindings"][0]["device_id"] = "missing"
        path = self.write_profile(payload)

        with self.assertConfigError(ORPHAN_BINDING):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_binding_url(self):
        payload = valid_profile()
        payload["http_bindings"][0]["base_url"] = "https://192.168.1.50"
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_BINDING):
            RuntimeConfigurationLoader().load(path)

    def test_embedded_credentials_rejected(self):
        payload = valid_profile()
        payload["http_bindings"][0]["base_url"] = "http://user:pass@192.168.1.50"
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_BINDING):
            RuntimeConfigurationLoader().load(path)

    def test_invalid_timeout(self):
        payload = valid_profile()
        payload["http_bindings"][0]["timeout_seconds"] = -1
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_BINDING):
            RuntimeConfigurationLoader().load(path)

    def test_unknown_binding_field_rejected(self):
        payload = valid_profile()
        payload["http_bindings"][0]["token"] = "secret"
        path = self.write_profile(payload)

        with self.assertConfigError(INVALID_BINDING):
            RuntimeConfigurationLoader().load(path)

    def test_materialize_devices(self):
        profile = RuntimeConfigurationLoader().load(self.write_profile(valid_profile()))

        devices = build_devices(profile)

        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].id, "lamp_1")
        self.assertEqual(devices[0].state.status, "unknown")
        self.assertEqual(devices[0].metadata, {})
        self.assertEqual(len(devices[0].capabilities), 2)
        self.assertTrue(
            all(isinstance(capability, DeviceCapability) for capability in devices[0].capabilities)
        )

    def test_materialize_http_bindings(self):
        profile = RuntimeConfigurationLoader().load(self.write_profile(valid_profile()))

        bindings = build_http_bindings(profile)

        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].device_id, "lamp_1")
        self.assertEqual(bindings[0].read_path, "/device/read")

    def test_configuration_error_string_exposes_only_code(self):
        error = ConfigurationError(CONFIG_INVALID, detail="http://192.168.1.50")

        self.assertEqual(str(error), CONFIG_INVALID)
        self.assertEqual(error.code, CONFIG_INVALID)

    def write_profile(self, payload):
        return self.write_json(payload)

    def write_json(self, payload):
        path = self.root / "profile.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def assertConfigError(self, code):
        return _ConfigurationErrorContext(self, code)


class _ConfigurationErrorContext:
    def __init__(self, test_case, code):
        self.test_case = test_case
        self.code = code
        self.context = None

    def __enter__(self):
        self.context = self.test_case.assertRaises(ConfigurationError)
        return self.context.__enter__()

    def __exit__(self, exc_type, exc, tb):
        result = self.context.__exit__(exc_type, exc, tb)
        self.test_case.assertEqual(self.context.exception.code, self.code)
        return result


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
                            "state": {
                                "type": "string",
                                "required": True,
                            }
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


if __name__ == "__main__":
    unittest.main()
