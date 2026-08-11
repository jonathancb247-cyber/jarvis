"""Experimental synchronous MQTT request/response driver for JarvisOS."""

from dataclasses import dataclass, field
import json
import string
from uuid import uuid4

from jarvis_core.devices import Device
from jarvis_core.drivers import (
    CONFIGURATION_INVALID,
    CONNECTION_FAILED,
    DRIVER_UNAVAILABLE,
    INVALID_DEVICE,
    INVALID_PARAMETERS,
    INVALID_RESPONSE,
    OPERATION_NOT_SUPPORTED,
    PROTOCOL_ERROR,
    REQUEST_TIMEOUT,
    DriverResult,
)


DEFAULT_TIMEOUT_SECONDS = 2.0
MAX_TIMEOUT_SECONDS = 10.0
MAX_TOPIC_LENGTH = 128
MAX_REQUEST_ID_LENGTH = 64
MAX_REQUEST_BYTES = 4096
MAX_RESPONSE_BYTES = 16384
MAX_ALLOWED_CAPABILITIES = 32
MAX_ALLOWED_RESPONSE_KEYS = 32
MAX_RESPONSE_KEY_LENGTH = 64
JSON_CONTENT_TYPE = "application/json"

ALLOWED_REMOTE_ERRORS = {
    DRIVER_UNAVAILABLE,
    CONFIGURATION_INVALID,
    CONNECTION_FAILED,
    REQUEST_TIMEOUT,
    PROTOCOL_ERROR,
    INVALID_RESPONSE,
    OPERATION_NOT_SUPPORTED,
}

RESPONSE_FIELDS = {"request_id", "ok", "semantic", "error"}
REQUEST_OPERATIONS = {"read", "apply"}


@dataclass(frozen=True)
class MQTTDeviceBinding:
    """Declarative MQTT request/response reachability for one Device."""

    device_id: str
    request_topic: str
    response_topic: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    allowed_capabilities: tuple = field(default_factory=tuple)
    allowed_response_keys: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if not _is_non_empty_string(self.device_id):
            raise ValueError("MQTTDeviceBinding device_id must be a non-empty string")
        _validate_topic(self.request_topic, "request_topic")
        _validate_topic(self.response_topic, "response_topic")
        if self.request_topic == self.response_topic:
            raise ValueError("MQTTDeviceBinding topics must be distinct")
        if not isinstance(self.timeout_seconds, (int, float)):
            raise ValueError("MQTTDeviceBinding timeout_seconds must be numeric")
        if self.timeout_seconds <= 0 or self.timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise ValueError("MQTTDeviceBinding timeout_seconds is out of range")
        _validate_string_tuple(
            self.allowed_capabilities,
            "allowed_capabilities",
            MAX_ALLOWED_CAPABILITIES,
        )
        _validate_string_tuple(
            self.allowed_response_keys,
            "allowed_response_keys",
            MAX_ALLOWED_RESPONSE_KEYS,
        )
        if not self.allowed_capabilities:
            raise ValueError("MQTTDeviceBinding allowed_capabilities must not be empty")
        if not self.allowed_response_keys:
            raise ValueError("MQTTDeviceBinding allowed_response_keys must not be empty")
        for key in self.allowed_response_keys:
            if len(key) > MAX_RESPONSE_KEY_LENGTH:
                raise ValueError("MQTTDeviceBinding response key is too long")


class MQTTDeviceBindingStore:
    """In-memory MQTT binding store keyed by device ID."""

    def __init__(self):
        self._bindings = {}

    def register(self, binding):
        if not isinstance(binding, MQTTDeviceBinding):
            raise TypeError("MQTTDeviceBindingStore.register expects MQTTDeviceBinding")
        if binding.device_id in self._bindings:
            raise ValueError(f"MQTT binding already registered: {binding.device_id}")
        self._bindings[binding.device_id] = binding

    def get(self, device_id):
        if device_id not in self._bindings:
            raise KeyError(f"MQTT binding not found: {device_id}")
        return self._bindings[device_id]

    def has(self, device_id):
        return device_id in self._bindings

    def list(self):
        return list(self._bindings.values())


class UnavailableMQTTClient:
    """Safe placeholder used when no real MQTT client is injected."""

    def publish(self, topic, payload):
        raise MQTTConnectionError()

    def wait_for_response(self, topic, correlation_id, timeout_seconds):
        raise MQTTConnectionError()

    def close(self):
        return None


class MQTTTimeoutError(Exception):
    """Internal timeout marker for MQTT transport."""


class MQTTConnectionError(Exception):
    """Internal broker/connectivity marker for MQTT transport."""


class MQTTPublishError(Exception):
    """Internal publish marker for MQTT transport."""


class MQTTClientClosedError(Exception):
    """Internal closed-client marker for MQTT transport."""


class MQTTResponseTooLargeError(Exception):
    """Internal response-size marker for MQTT transport."""


class MQTTInvalidJsonError(Exception):
    """Internal JSON marker for MQTT transport."""


class MQTTDeviceDriver:
    """Experimental synchronous MQTT request/response driver."""

    def __init__(
        self,
        binding_store,
        client=None,
        max_request_bytes=MAX_REQUEST_BYTES,
        max_response_bytes=MAX_RESPONSE_BYTES,
        request_id_factory=None,
    ):
        if not isinstance(binding_store, MQTTDeviceBindingStore):
            raise TypeError("MQTTDeviceDriver expects an MQTTDeviceBindingStore")
        client = client or UnavailableMQTTClient()
        for method_name in ("publish", "wait_for_response", "close"):
            if not callable(getattr(client, method_name, None)):
                raise TypeError(f"MQTT client must define {method_name}")
        if not isinstance(max_request_bytes, int) or max_request_bytes <= 0:
            raise ValueError("max_request_bytes must be a positive integer")
        if not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be a positive integer")
        if request_id_factory is not None and not callable(request_id_factory):
            raise TypeError("request_id_factory must be callable")
        self.binding_store = binding_store
        self.client = client
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes
        self._request_id_factory = request_id_factory or _default_request_id

    def read(self, device, capability_name):
        return self._execute(device, capability_name, {}, "read")

    def apply(self, device, capability_name, parameters):
        if not isinstance(parameters, dict):
            return DriverResult(False, {}, INVALID_PARAMETERS)
        return self._execute(device, capability_name, parameters.copy(), "apply")

    def close(self):
        try:
            self.client.close()
        except Exception:
            return None
        return None

    def _execute(self, device, capability_name, parameters, operation):
        if not isinstance(device, Device):
            return DriverResult(False, {}, INVALID_DEVICE)
        if not _is_non_empty_string(capability_name):
            return DriverResult(False, {}, CONFIGURATION_INVALID)
        if operation not in REQUEST_OPERATIONS:
            return DriverResult(False, {}, CONFIGURATION_INVALID)

        try:
            binding = self.binding_store.get(device.id)
        except KeyError:
            return DriverResult(False, {}, DRIVER_UNAVAILABLE)
        if capability_name not in binding.allowed_capabilities:
            return DriverResult(False, {}, OPERATION_NOT_SUPPORTED)

        request_id = self._new_request_id()
        if request_id is None:
            return DriverResult(False, {}, CONFIGURATION_INVALID)
        payload = self._request_payload(
            request_id,
            device.id,
            capability_name,
            operation,
            parameters,
        )
        if payload is None:
            return DriverResult(False, {}, CONFIGURATION_INVALID)

        try:
            self.client.publish(binding.request_topic, payload)
            response = self.client.wait_for_response(
                binding.response_topic,
                request_id,
                binding.timeout_seconds,
            )
        except MQTTTimeoutError:
            return DriverResult(False, {}, REQUEST_TIMEOUT)
        except MQTTResponseTooLargeError:
            return DriverResult(False, {}, INVALID_RESPONSE)
        except MQTTInvalidJsonError:
            return DriverResult(False, {}, INVALID_RESPONSE)
        except (MQTTConnectionError, MQTTPublishError, MQTTClientClosedError):
            return DriverResult(False, {}, CONNECTION_FAILED)
        except Exception:
            return DriverResult(False, {}, CONNECTION_FAILED)

        return self._driver_result_from_response(response, request_id, binding)

    def _new_request_id(self):
        request_id = self._request_id_factory()
        if not isinstance(request_id, str) or not request_id:
            return None
        if len(request_id) > MAX_REQUEST_ID_LENGTH:
            return None
        if any(character not in string.ascii_letters + string.digits + "-_" for character in request_id):
            return None
        return request_id

    def _request_payload(
        self,
        request_id,
        device_id,
        capability_name,
        operation,
        parameters,
    ):
        envelope = {
            "request_id": request_id,
            "device_id": device_id,
            "capability": capability_name,
            "operation": operation,
            "parameters": parameters.copy(),
        }
        try:
            payload = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        except Exception:
            return None
        if len(payload) > self.max_request_bytes:
            return None
        return payload

    def _driver_result_from_response(self, response, request_id, binding):
        try:
            payload = _decode_response(response, self.max_response_bytes)
        except (MQTTResponseTooLargeError, MQTTInvalidJsonError):
            return DriverResult(False, {}, INVALID_RESPONSE)
        if not isinstance(payload, dict):
            return DriverResult(False, {}, INVALID_RESPONSE)
        if set(payload.keys()) != RESPONSE_FIELDS:
            return DriverResult(False, {}, INVALID_RESPONSE)
        if payload["request_id"] != request_id:
            return DriverResult(False, {}, INVALID_RESPONSE)
        ok = payload["ok"]
        semantic = payload["semantic"]
        error = payload["error"]
        if not isinstance(ok, bool):
            return DriverResult(False, {}, INVALID_RESPONSE)
        if not isinstance(semantic, dict):
            return DriverResult(False, {}, INVALID_RESPONSE)
        if error is not None and not _is_non_empty_string(error):
            return DriverResult(False, {}, INVALID_RESPONSE)

        if ok:
            if error is not None:
                return DriverResult(False, {}, INVALID_RESPONSE)
            if not _semantic_keys_allowed(semantic, binding.allowed_response_keys):
                return DriverResult(False, {}, INVALID_RESPONSE)
            return DriverResult(True, semantic.copy(), None)
        if semantic:
            return DriverResult(False, {}, INVALID_RESPONSE)
        if error in ALLOWED_REMOTE_ERRORS:
            return DriverResult(False, {}, error)
        return DriverResult(False, {}, PROTOCOL_ERROR)


def _default_request_id():
    return uuid4().hex


def _decode_response(response, max_response_bytes):
    if isinstance(response, dict):
        return response
    if isinstance(response, bytes):
        if len(response) > max_response_bytes:
            raise MQTTResponseTooLargeError()
        raw = response
    elif isinstance(response, str):
        raw = response.encode("utf-8")
        if len(raw) > max_response_bytes:
            raise MQTTResponseTooLargeError()
    else:
        raise MQTTInvalidJsonError()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as error:
        raise MQTTInvalidJsonError() from error


def _semantic_keys_allowed(semantic, allowed_response_keys):
    allowed = set(allowed_response_keys)
    for key in semantic:
        if not _is_non_empty_string(key):
            return False
        if key not in allowed:
            return False
    return True


def _validate_topic(topic, field_name):
    if not _is_non_empty_string(topic):
        raise ValueError(f"MQTTDeviceBinding {field_name} must be a non-empty string")
    if topic.strip() != topic:
        raise ValueError(f"MQTTDeviceBinding {field_name} must not have outer spaces")
    if len(topic) > MAX_TOPIC_LENGTH:
        raise ValueError(f"MQTTDeviceBinding {field_name} is too long")
    if "#" in topic or "+" in topic:
        raise ValueError(f"MQTTDeviceBinding {field_name} must not use wildcards")
    if any(ord(character) < 32 or ord(character) == 127 for character in topic):
        raise ValueError(f"MQTTDeviceBinding {field_name} must not contain control characters")


def _validate_string_tuple(values, field_name, maximum):
    if not isinstance(values, tuple):
        raise ValueError(f"MQTTDeviceBinding {field_name} must be a tuple")
    if len(values) > maximum:
        raise ValueError(f"MQTTDeviceBinding {field_name} is too large")
    seen = set()
    for value in values:
        if not _is_non_empty_string(value):
            raise ValueError(f"MQTTDeviceBinding {field_name} values must be strings")
        if value in seen:
            raise ValueError(f"MQTTDeviceBinding {field_name} values must be unique")
        seen.add(value)


def _is_non_empty_string(value):
    return isinstance(value, str) and bool(value)
