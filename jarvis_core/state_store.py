"""Minimal JSON DeviceState persistence boundary for JarvisOS."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import DeviceRegistry, DeviceState


STATE_STORE_SCHEMA_VERSION = 1
MAX_STATE_STORE_BYTES = 65536
MAX_STATES = 1000
MAX_PROPERTIES = 100
MAX_JSON_DEPTH = 6

STATE_STORE_UNAVAILABLE = "state_store_unavailable"
STATE_STORE_CORRUPT = "state_store_corrupt"
STATE_RESTORE_FAILED = "state_restore_failed"
STATE_SAVE_FAILED = "state_save_failed"
SCHEMA_VERSION_UNSUPPORTED = "schema_version_unsupported"

ROOT_FIELDS = {"schema_version", "states"}
STATE_FIELDS = {"status", "properties", "updated_at"}
FORBIDDEN_PROPERTY_KEYS = {
    "args",
    "binding",
    "candidate",
    "command",
    "credentials",
    "driver_result",
    "error",
    "exception",
    "headers",
    "host",
    "ip",
    "payload",
    "raw_payload",
    "request",
    "response",
    "secret",
    "stack_trace",
    "timeout",
    "token",
    "traceback",
    "trust",
    "url",
}

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class StateStoreError(Exception):
    """Safe internal error for DeviceState persistence failures."""

    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


class JsonDeviceStateStore:
    """Stores semantic DeviceState snapshots as validated JSON."""

    def __init__(self, path):
        if not isinstance(path, (str, Path)) or not str(path):
            raise StateStoreError(STATE_STORE_UNAVAILABLE)
        self.path = Path(path)

    def load(self):
        """Load a validated snapshot. Missing files are treated as empty."""
        if not self.path.exists():
            return {}
        if not self.path.is_file():
            raise StateStoreError(STATE_STORE_UNAVAILABLE)
        try:
            size = self.path.stat().st_size
        except OSError as error:
            raise StateStoreError(STATE_STORE_UNAVAILABLE) from error
        if size <= 0 or size > MAX_STATE_STORE_BYTES:
            raise StateStoreError(STATE_STORE_CORRUPT)

        try:
            raw = self.path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise StateStoreError(STATE_STORE_CORRUPT) from error
        except OSError as error:
            raise StateStoreError(STATE_STORE_UNAVAILABLE) from error

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise StateStoreError(STATE_STORE_CORRUPT) from error
        return self._parse_snapshot(payload)

    def save(self, states):
        """Atomically save the supplied official DeviceState snapshot."""
        snapshot = self._serialize_snapshot(states)
        encoded = json.dumps(snapshot, sort_keys=True, indent=2) + "\n"
        if len(encoded.encode("utf-8")) > MAX_STATE_STORE_BYTES:
            raise StateStoreError(STATE_SAVE_FAILED)

        parent = self.path.parent
        temp_path = parent / (self.path.name + ".tmp")
        try:
            parent.mkdir(parents=True, exist_ok=True)
            with temp_path.open("w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        except OSError as error:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            raise StateStoreError(STATE_SAVE_FAILED) from error

    def _parse_snapshot(self, payload):
        if not isinstance(payload, dict):
            raise StateStoreError(STATE_STORE_CORRUPT)
        _require_exact_fields(payload, ROOT_FIELDS)
        if payload["schema_version"] != STATE_STORE_SCHEMA_VERSION:
            raise StateStoreError(SCHEMA_VERSION_UNSUPPORTED)
        states_payload = payload["states"]
        if not isinstance(states_payload, dict):
            raise StateStoreError(STATE_STORE_CORRUPT)
        if len(states_payload) > MAX_STATES:
            raise StateStoreError(STATE_STORE_CORRUPT)

        states = {}
        for device_id, state_payload in states_payload.items():
            if not _is_non_empty_string(device_id):
                raise StateStoreError(STATE_STORE_CORRUPT)
            states[device_id] = self._parse_state(state_payload)
        return states

    def _parse_state(self, payload):
        if not isinstance(payload, dict):
            raise StateStoreError(STATE_STORE_CORRUPT)
        _require_exact_fields(payload, STATE_FIELDS)
        status = payload["status"]
        properties = payload["properties"]
        updated_at = payload["updated_at"]
        if not _is_non_empty_string(status):
            raise StateStoreError(STATE_STORE_CORRUPT)
        if not isinstance(properties, dict):
            raise StateStoreError(STATE_STORE_CORRUPT)
        if len(properties) > MAX_PROPERTIES:
            raise StateStoreError(STATE_STORE_CORRUPT)
        if _json_depth(properties) > MAX_JSON_DEPTH:
            raise StateStoreError(STATE_STORE_CORRUPT)
        if not _is_valid_json_value(properties) or _has_forbidden_property_keys(properties):
            raise StateStoreError(STATE_STORE_CORRUPT)
        if not _is_iso_datetime(updated_at):
            raise StateStoreError(STATE_STORE_CORRUPT)

        restored_status = "unknown" if status == "unknown" else "stale"
        return DeviceState(
            status=restored_status,
            properties=deepcopy(properties),
            updated_at=updated_at,
        )

    def _serialize_snapshot(self, states):
        if not isinstance(states, dict):
            raise StateStoreError(STATE_SAVE_FAILED)
        if len(states) > MAX_STATES:
            raise StateStoreError(STATE_SAVE_FAILED)
        serialized_states = {}
        for device_id, state in states.items():
            if not _is_non_empty_string(device_id):
                raise StateStoreError(STATE_SAVE_FAILED)
            if not isinstance(state, DeviceState):
                raise StateStoreError(STATE_SAVE_FAILED)
            properties = deepcopy(state.properties)
            if len(properties) > MAX_PROPERTIES:
                raise StateStoreError(STATE_SAVE_FAILED)
            if _json_depth(properties) > MAX_JSON_DEPTH:
                raise StateStoreError(STATE_SAVE_FAILED)
            if not _is_valid_json_value(properties) or _has_forbidden_property_keys(properties):
                raise StateStoreError(STATE_SAVE_FAILED)
            updated_at = state.updated_at or datetime.now(timezone.utc).isoformat()
            if not _is_iso_datetime(updated_at):
                raise StateStoreError(STATE_SAVE_FAILED)
            serialized_states[device_id] = {
                "status": state.status,
                "properties": properties,
                "updated_at": updated_at,
            }
        return {
            "schema_version": STATE_STORE_SCHEMA_VERSION,
            "states": serialized_states,
        }


class DeviceStatePersistence:
    """Persists official states from a DeviceRegistry snapshot."""

    def __init__(self, device_registry, state_store):
        if not isinstance(device_registry, DeviceRegistry):
            raise TypeError("DeviceStatePersistence expects a DeviceRegistry")
        if not isinstance(state_store, JsonDeviceStateStore):
            raise TypeError("DeviceStatePersistence expects a JsonDeviceStateStore")
        self.device_registry = device_registry
        self.state_store = state_store

    def restore(self):
        states = self.state_store.load()
        for device in self.device_registry.list():
            if device.id in states:
                self.device_registry.update_state(device.id, states[device.id])

    def save_snapshot(self):
        states = {
            device.id: device.state
            for device in self.device_registry.list()
        }
        self.state_store.save(states)

    def save_snapshot_best_effort(self):
        try:
            self.save_snapshot()
        except StateStoreError:
            logger.warning("device state snapshot save failed")


class PersistingDeviceStateCoordinator(DeviceStateCoordinator):
    """Wraps DeviceStateCoordinator and persists after official state changes."""

    def __init__(self, coordinator, persistence):
        if not isinstance(coordinator, DeviceStateCoordinator):
            raise TypeError("coordinator must be a DeviceStateCoordinator")
        if not isinstance(persistence, DeviceStatePersistence):
            raise TypeError("persistence must be DeviceStatePersistence")
        self._coordinator = coordinator
        self._persistence = persistence

    def coordinate(self, device, capability_name, operation, driver_result, registry):
        before = device.state
        state = self._coordinator.coordinate(
            device,
            capability_name,
            operation,
            driver_result,
            registry,
        )
        if state is not before:
            self._persistence.save_snapshot_best_effort()
        return state


def _is_non_empty_string(value):
    return isinstance(value, str) and bool(value)


def _require_exact_fields(payload, allowed):
    if set(payload.keys()) != allowed:
        raise StateStoreError(STATE_STORE_CORRUPT)


def _is_iso_datetime(value):
    if not _is_non_empty_string(value):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_valid_json_value(value):
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


def _json_depth(value):
    if isinstance(value, dict):
        if not value:
            return 1
        return 1 + max(_json_depth(item) for item in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(_json_depth(item) for item in value)
    return 1


def _has_forbidden_property_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return True
            if key.lower() in FORBIDDEN_PROPERTY_KEYS:
                return True
            if _has_forbidden_property_keys(item):
                return True
    if isinstance(value, list):
        return any(_has_forbidden_property_keys(item) for item in value)
    return False
