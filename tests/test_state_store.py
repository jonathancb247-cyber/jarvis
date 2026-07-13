import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from jarvis_core.devices import Device, DeviceRegistry, DeviceState
from jarvis_core.state_store import (
    SCHEMA_VERSION_UNSUPPORTED,
    STATE_SAVE_FAILED,
    STATE_STORE_CORRUPT,
    STATE_STORE_UNAVAILABLE,
    DeviceStatePersistence,
    JsonDeviceStateStore,
    StateStoreError,
)


class JsonDeviceStateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.path = self.root / "state" / "devices.state.json"

    def test_missing_file_loads_empty_snapshot(self):
        store = JsonDeviceStateStore(self.path)

        self.assertEqual(store.load(), {})

    def test_loads_empty_states(self):
        self.write_snapshot({"schema_version": 1, "states": {}})

        states = JsonDeviceStateStore(self.path).load()

        self.assertEqual(states, {})

    def test_loads_unknown_state_as_unknown(self):
        self.write_snapshot(
            {
                "schema_version": 1,
                "states": {
                    "lamp_1": {
                        "status": "unknown",
                        "properties": {"power": False},
                        "updated_at": "2026-07-13T12:00:00+00:00",
                    }
                },
            }
        )

        state = JsonDeviceStateStore(self.path).load()["lamp_1"]

        self.assertEqual(state.status, "unknown")
        self.assertEqual(state.properties, {"power": False})
        self.assertEqual(state.updated_at, "2026-07-13T12:00:00+00:00")

    def test_known_stored_state_becomes_stale(self):
        self.write_snapshot(
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
        )

        state = JsonDeviceStateStore(self.path).load()["lamp_1"]

        self.assertEqual(state.status, "stale")
        self.assertEqual(state.properties, {"power": True})

    def test_loads_multiple_states(self):
        self.write_snapshot(
            {
                "schema_version": 1,
                "states": {
                    "lamp_1": valid_state_payload(),
                    "lamp_2": valid_state_payload(power=False),
                },
            }
        )

        states = JsonDeviceStateStore(self.path).load()

        self.assertEqual(set(states.keys()), {"lamp_1", "lamp_2"})

    def test_directory_path_is_unavailable(self):
        self.path.mkdir(parents=True)

        with self.assertStateError(STATE_STORE_UNAVAILABLE):
            JsonDeviceStateStore(self.path).load()

    def test_oversized_file_is_corrupt(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(" " * 70000, encoding="utf-8")

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_invalid_utf8_is_corrupt(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"\xff")

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_invalid_json_is_corrupt(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{", encoding="utf-8")

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_root_must_be_object(self):
        self.write_snapshot([])

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_unknown_root_field_rejected(self):
        payload = {"schema_version": 1, "states": {}, "debug": {}}
        self.write_snapshot(payload)

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_unsupported_schema_rejected(self):
        self.write_snapshot({"schema_version": 2, "states": {}})

        with self.assertStateError(SCHEMA_VERSION_UNSUPPORTED):
            JsonDeviceStateStore(self.path).load()

    def test_states_must_be_object(self):
        self.write_snapshot({"schema_version": 1, "states": []})

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_state_unknown_fields_rejected(self):
        payload = valid_snapshot()
        payload["states"]["lamp_1"]["url"] = "http://192.168.1.50"
        self.write_snapshot(payload)

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_invalid_status_rejected(self):
        payload = valid_snapshot()
        payload["states"]["lamp_1"]["status"] = ""
        self.write_snapshot(payload)

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_invalid_properties_rejected(self):
        payload = valid_snapshot()
        payload["states"]["lamp_1"]["properties"] = []
        self.write_snapshot(payload)

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_invalid_updated_at_rejected(self):
        payload = valid_snapshot()
        payload["states"]["lamp_1"]["updated_at"] = "not-a-date"
        self.write_snapshot(payload)

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_too_many_properties_rejected(self):
        payload = valid_snapshot()
        payload["states"]["lamp_1"]["properties"] = {
            f"p{i}": i for i in range(101)
        }
        self.write_snapshot(payload)

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_excessive_nesting_rejected(self):
        payload = valid_snapshot()
        payload["states"]["lamp_1"]["properties"] = {
            "a": {"b": {"c": {"d": {"e": {"f": {"g": True}}}}}}
        }
        self.write_snapshot(payload)

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_technical_property_keys_rejected_on_load(self):
        payload = valid_snapshot()
        payload["states"]["lamp_1"]["properties"] = {"url": "http://192.168.1.50"}
        self.write_snapshot(payload)

        with self.assertStateError(STATE_STORE_CORRUPT):
            JsonDeviceStateStore(self.path).load()

    def test_save_writes_deterministic_json_and_creates_parent(self):
        store = JsonDeviceStateStore(self.path)

        store.save({"lamp_1": DeviceState("known", {"power": True}, "2026-07-13T12:00:00+00:00")})

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["states"]["lamp_1"]["properties"], {"power": True})
        self.assertFalse((self.path.parent / (self.path.name + ".tmp")).exists())

    def test_save_rejects_invalid_state_map(self):
        with self.assertStateError(STATE_SAVE_FAILED):
            JsonDeviceStateStore(self.path).save({"lamp_1": object()})

    def test_save_rejects_technical_property_keys(self):
        with self.assertStateError(STATE_SAVE_FAILED):
            JsonDeviceStateStore(self.path).save(
                {
                    "lamp_1": DeviceState(
                        "known",
                        {"payload": {"raw": True}},
                        "2026-07-13T12:00:00+00:00",
                    )
                }
            )

    def test_save_failure_does_not_leave_temp_file(self):
        store = JsonDeviceStateStore(self.path)

        with patch("os.replace", side_effect=OSError("replace failed")):
            with self.assertStateError(STATE_SAVE_FAILED):
                store.save(
                    {
                        "lamp_1": DeviceState(
                            "known",
                            {"power": True},
                            "2026-07-13T12:00:00+00:00",
                        )
                    }
                )

        self.assertFalse((self.path.parent / (self.path.name + ".tmp")).exists())
        self.assertFalse(self.path.exists())

    def test_error_string_exposes_only_code(self):
        error = StateStoreError(STATE_STORE_CORRUPT, detail={"power": True})

        self.assertEqual(str(error), STATE_STORE_CORRUPT)

    def write_snapshot(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            self.path.write_text(payload, encoding="utf-8")
        else:
            self.path.write_text(json.dumps(payload), encoding="utf-8")

    def assertStateError(self, code):
        return _StateStoreErrorContext(self, code)


class DeviceStatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.path = self.root / "state" / "devices.state.json"

    def test_restore_only_updates_registered_devices(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "states": {
                        "lamp_1": valid_state_payload(),
                        "orphan": valid_state_payload(power=False),
                    },
                }
            ),
            encoding="utf-8",
        )
        registry = DeviceRegistry()
        registry.register(Device("lamp_1", "Lamp", "light"))

        DeviceStatePersistence(registry, JsonDeviceStateStore(self.path)).restore()

        self.assertEqual(registry.get("lamp_1").state.status, "stale")
        self.assertEqual(registry.get("lamp_1").state.properties, {"power": True})
        with self.assertRaises(KeyError):
            registry.get("orphan")

    def test_save_snapshot_uses_registry_devices_only(self):
        registry = DeviceRegistry()
        registry.register(
            Device(
                "lamp_1",
                "Lamp",
                "light",
                state=DeviceState(
                    "known",
                    {"power": True},
                    "2026-07-13T12:00:00+00:00",
                ),
            )
        )

        DeviceStatePersistence(registry, JsonDeviceStateStore(self.path)).save_snapshot()

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(set(payload["states"].keys()), {"lamp_1"})


class _StateStoreErrorContext:
    def __init__(self, test_case, code):
        self.test_case = test_case
        self.code = code
        self.context = None

    def __enter__(self):
        self.context = self.test_case.assertRaises(StateStoreError)
        return self.context.__enter__()

    def __exit__(self, exc_type, exc, tb):
        result = self.context.__exit__(exc_type, exc, tb)
        self.test_case.assertEqual(self.context.exception.code, self.code)
        return result


def valid_snapshot():
    return {
        "schema_version": 1,
        "states": {
            "lamp_1": valid_state_payload(),
        },
    }


def valid_state_payload(power=True):
    return {
        "status": "known",
        "properties": {"power": power},
        "updated_at": "2026-07-13T12:00:00+00:00",
    }


if __name__ == "__main__":
    unittest.main()
