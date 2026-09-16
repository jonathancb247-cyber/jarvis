"""Declarative runtime configuration loading for JarvisOS."""

from dataclasses import dataclass, field
import json
from pathlib import Path

from jarvis_core.devices import Device, DeviceCapability, DeviceState, room_label
from jarvis_core.http_driver import HttpDeviceBinding
from jarvis_core.mqtt_driver import MQTTDeviceBinding


SUPPORTED_SCHEMA_VERSION = 1
MAX_CONFIGURATION_BYTES = 65536

CONFIG_NOT_FOUND = "config_not_found"
CONFIG_INVALID = "config_invalid"
SCHEMA_VERSION_UNSUPPORTED = "schema_version_unsupported"
DUPLICATE_DEVICE = "duplicate_device"
INVALID_CAPABILITY = "invalid_capability"
INVALID_BINDING = "invalid_binding"
ORPHAN_BINDING = "orphan_binding"

ROOT_FIELDS = {
    "schema_version",
    "profile",
    "devices",
    "http_bindings",
    "mqtt_bindings",
    "runtime_options",
}
REQUIRED_ROOT_FIELDS = ROOT_FIELDS - {"mqtt_bindings"}
DEVICE_FIELDS = {"id", "name", "type", "capabilities", "metadata"}
CAPABILITY_FIELDS = {
    "name",
    "kind",
    "parameters",
    "constraints",
    "availability_policy",
}
PARAMETER_DESCRIPTOR_FIELDS = {"type", "required", "constraints", "metadata"}
BINDING_FIELDS = {
    "device_id",
    "base_url",
    "timeout_seconds",
    "read_path",
    "apply_path",
}
MQTT_BINDING_FIELDS = {
    "transport",
    "device_id",
    "request_topic",
    "response_topic",
    "timeout_seconds",
    "allowed_capabilities",
    "allowed_response_keys",
}
RUNTIME_OPTION_FIELDS = {"state_store_path"}


class ConfigurationError(Exception):
    """Safe startup error for declarative configuration failures."""

    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class DeviceCapabilityConfig:
    """Declarative DeviceCapability configuration."""

    name: str
    kind: str
    parameters: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)
    availability_policy: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceConfig:
    """Declarative Device configuration."""

    id: str
    name: str
    type: str
    capabilities: tuple = field(default_factory=tuple)
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HttpDeviceBindingConfig:
    """Declarative HTTP binding configuration."""

    device_id: str
    base_url: str
    timeout_seconds: float
    read_path: str
    apply_path: str


@dataclass(frozen=True)
class MQTTDeviceBindingConfig:
    """Declarative MQTT binding configuration."""

    device_id: str
    request_topic: str
    response_topic: str
    timeout_seconds: float
    allowed_capabilities: tuple
    allowed_response_keys: tuple


@dataclass(frozen=True)
class RuntimeProfile:
    """Validated declarative runtime profile data."""

    schema_version: int
    name: str
    devices: tuple = field(default_factory=tuple)
    http_bindings: tuple = field(default_factory=tuple)
    mqtt_bindings: tuple = field(default_factory=tuple)
    runtime_options: dict = field(default_factory=dict)


class RuntimeConfigurationLoader:
    """Load and validate a RuntimeProfile from explicit JSON configuration."""

    def load(self, path):
        config_path = self._validate_path(path)
        payload = self._read_json(config_path)
        return self._parse_profile(payload)

    def _validate_path(self, path):
        if not isinstance(path, (str, Path)) or not str(path):
            raise ConfigurationError(CONFIG_INVALID)
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigurationError(CONFIG_NOT_FOUND)
        if not config_path.is_file():
            raise ConfigurationError(CONFIG_INVALID)
        try:
            size = config_path.stat().st_size
        except OSError as error:
            raise ConfigurationError(CONFIG_INVALID) from error
        if size <= 0 or size > MAX_CONFIGURATION_BYTES:
            raise ConfigurationError(CONFIG_INVALID)
        return config_path

    def _read_json(self, path):
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ConfigurationError(CONFIG_INVALID) from error
        except OSError as error:
            raise ConfigurationError(CONFIG_INVALID) from error
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise ConfigurationError(CONFIG_INVALID) from error

    def _parse_profile(self, payload):
        if not isinstance(payload, dict):
            raise ConfigurationError(CONFIG_INVALID)
        _require_required_allowed_fields(
            payload,
            REQUIRED_ROOT_FIELDS,
            ROOT_FIELDS,
            CONFIG_INVALID,
        )

        schema_version = payload["schema_version"]
        if schema_version != SUPPORTED_SCHEMA_VERSION:
            raise ConfigurationError(SCHEMA_VERSION_UNSUPPORTED)
        profile_name = payload["profile"]
        if not isinstance(profile_name, str) or not profile_name:
            raise ConfigurationError(CONFIG_INVALID)
        devices_payload = payload["devices"]
        bindings_payload = payload["http_bindings"]
        mqtt_bindings_payload = payload.get("mqtt_bindings", [])
        runtime_options = payload["runtime_options"]
        if not isinstance(devices_payload, list):
            raise ConfigurationError(CONFIG_INVALID)
        if not isinstance(bindings_payload, list):
            raise ConfigurationError(CONFIG_INVALID)
        if not isinstance(mqtt_bindings_payload, list):
            raise ConfigurationError(CONFIG_INVALID)
        if not isinstance(runtime_options, dict):
            raise ConfigurationError(CONFIG_INVALID)
        runtime_options = self._parse_runtime_options(runtime_options)

        devices = self._parse_devices(devices_payload)
        device_ids = {device.id for device in devices}
        bindings = self._parse_bindings(bindings_payload, device_ids)
        mqtt_bindings = self._parse_mqtt_bindings(
            mqtt_bindings_payload,
            device_ids,
            {binding.device_id for binding in bindings},
        )
        return RuntimeProfile(
            schema_version=schema_version,
            name=profile_name,
            devices=tuple(devices),
            http_bindings=tuple(bindings),
            mqtt_bindings=tuple(mqtt_bindings),
            runtime_options=runtime_options,
        )

    def _parse_runtime_options(self, runtime_options):
        _require_allowed_fields(runtime_options, RUNTIME_OPTION_FIELDS, CONFIG_INVALID)
        parsed = {}
        if "state_store_path" in runtime_options:
            state_store_path = runtime_options["state_store_path"]
            if not _is_valid_local_path_string(state_store_path):
                raise ConfigurationError(CONFIG_INVALID)
            parsed["state_store_path"] = state_store_path
        return parsed

    def _parse_devices(self, devices_payload):
        devices = []
        seen_ids = set()
        for item in devices_payload:
            if not isinstance(item, dict):
                raise ConfigurationError(CONFIG_INVALID)
            _require_exact_fields(item, DEVICE_FIELDS, CONFIG_INVALID)
            if "state" in item:
                raise ConfigurationError(CONFIG_INVALID)
            device_id = item["id"]
            name = item["name"]
            device_type = item["type"]
            capabilities_payload = item["capabilities"]
            metadata = item["metadata"]
            if not _is_non_empty_string(device_id):
                raise ConfigurationError(CONFIG_INVALID)
            if device_id in seen_ids:
                raise ConfigurationError(DUPLICATE_DEVICE)
            seen_ids.add(device_id)
            if not _is_non_empty_string(name) or not _is_non_empty_string(device_type):
                raise ConfigurationError(CONFIG_INVALID)
            if not isinstance(capabilities_payload, list):
                raise ConfigurationError(CONFIG_INVALID)
            if not isinstance(metadata, dict):
                raise ConfigurationError(CONFIG_INVALID)
            capabilities = self._parse_capabilities(capabilities_payload)
            devices.append(
                DeviceConfig(
                    id=device_id,
                    name=name,
                    type=device_type,
                    capabilities=tuple(capabilities),
                    metadata=_parse_device_metadata(metadata),
                )
            )
        return devices

    def _parse_capabilities(self, capabilities_payload):
        capabilities = []
        seen_names = set()
        for item in capabilities_payload:
            if not isinstance(item, dict):
                raise ConfigurationError(INVALID_CAPABILITY)
            _require_exact_fields(item, CAPABILITY_FIELDS, INVALID_CAPABILITY)
            name = item["name"]
            kind = item["kind"]
            parameters = item["parameters"]
            constraints = item["constraints"]
            availability_policy = item["availability_policy"]
            if not _is_non_empty_string(name):
                raise ConfigurationError(INVALID_CAPABILITY)
            if name in seen_names:
                raise ConfigurationError(INVALID_CAPABILITY)
            seen_names.add(name)
            if kind not in {"action", "reading"}:
                raise ConfigurationError(INVALID_CAPABILITY)
            if not isinstance(parameters, dict):
                raise ConfigurationError(INVALID_CAPABILITY)
            self._validate_parameters(parameters)
            if not isinstance(constraints, dict):
                raise ConfigurationError(INVALID_CAPABILITY)
            if not isinstance(availability_policy, dict):
                raise ConfigurationError(INVALID_CAPABILITY)
            capabilities.append(
                DeviceCapabilityConfig(
                    name=name,
                    kind=kind,
                    parameters=_deep_copy_dict(parameters),
                    constraints=constraints.copy(),
                    availability_policy=availability_policy.copy(),
                )
            )
        return capabilities

    def _validate_parameters(self, parameters):
        for parameter_name, descriptor in parameters.items():
            if not _is_non_empty_string(parameter_name):
                raise ConfigurationError(INVALID_CAPABILITY)
            if not isinstance(descriptor, dict):
                raise ConfigurationError(INVALID_CAPABILITY)
            _require_allowed_fields(
                descriptor,
                PARAMETER_DESCRIPTOR_FIELDS,
                INVALID_CAPABILITY,
            )
            if "type" in descriptor and not _is_non_empty_string(descriptor["type"]):
                raise ConfigurationError(INVALID_CAPABILITY)
            if "required" in descriptor and not isinstance(descriptor["required"], bool):
                raise ConfigurationError(INVALID_CAPABILITY)
            if "constraints" in descriptor and not isinstance(
                descriptor["constraints"],
                dict,
            ):
                raise ConfigurationError(INVALID_CAPABILITY)
            if "metadata" in descriptor and not isinstance(descriptor["metadata"], dict):
                raise ConfigurationError(INVALID_CAPABILITY)

    def _parse_bindings(self, bindings_payload, device_ids):
        bindings = []
        seen_ids = set()
        for item in bindings_payload:
            if not isinstance(item, dict):
                raise ConfigurationError(INVALID_BINDING)
            _require_exact_fields(item, BINDING_FIELDS, INVALID_BINDING)
            device_id = item["device_id"]
            if not _is_non_empty_string(device_id):
                raise ConfigurationError(INVALID_BINDING)
            if device_id not in device_ids:
                raise ConfigurationError(ORPHAN_BINDING)
            if device_id in seen_ids:
                raise ConfigurationError(INVALID_BINDING)
            seen_ids.add(device_id)
            try:
                # Reuse the implemented HTTP binding contract as second-line validation.
                binding = HttpDeviceBinding(
                    device_id=device_id,
                    base_url=item["base_url"],
                    timeout_seconds=item["timeout_seconds"],
                    read_path=item["read_path"],
                    apply_path=item["apply_path"],
                )
            except Exception as error:
                raise ConfigurationError(INVALID_BINDING) from error
            bindings.append(
                HttpDeviceBindingConfig(
                    device_id=binding.device_id,
                    base_url=binding.base_url,
                    timeout_seconds=binding.timeout_seconds,
                    read_path=binding.read_path,
                    apply_path=binding.apply_path,
                )
            )
        return bindings

    def _parse_mqtt_bindings(self, bindings_payload, device_ids, bound_device_ids):
        bindings = []
        seen_ids = set()
        for item in bindings_payload:
            if not isinstance(item, dict):
                raise ConfigurationError(INVALID_BINDING)
            _require_exact_fields(item, MQTT_BINDING_FIELDS, INVALID_BINDING)
            if item["transport"] != "mqtt":
                raise ConfigurationError(INVALID_BINDING)
            device_id = item["device_id"]
            if not _is_non_empty_string(device_id):
                raise ConfigurationError(INVALID_BINDING)
            if device_id not in device_ids:
                raise ConfigurationError(ORPHAN_BINDING)
            if device_id in seen_ids or device_id in bound_device_ids:
                raise ConfigurationError(INVALID_BINDING)
            seen_ids.add(device_id)
            try:
                binding = MQTTDeviceBinding(
                    device_id=device_id,
                    request_topic=item["request_topic"],
                    response_topic=item["response_topic"],
                    timeout_seconds=item["timeout_seconds"],
                    allowed_capabilities=_string_tuple(
                        item["allowed_capabilities"],
                    ),
                    allowed_response_keys=_string_tuple(
                        item["allowed_response_keys"],
                    ),
                )
            except Exception as error:
                raise ConfigurationError(INVALID_BINDING) from error
            bindings.append(
                MQTTDeviceBindingConfig(
                    device_id=binding.device_id,
                    request_topic=binding.request_topic,
                    response_topic=binding.response_topic,
                    timeout_seconds=binding.timeout_seconds,
                    allowed_capabilities=binding.allowed_capabilities,
                    allowed_response_keys=binding.allowed_response_keys,
                )
            )
        return bindings


def build_devices(profile):
    """Materialize declarative Devices from a validated RuntimeProfile."""
    _ensure_profile(profile)
    devices = []
    for device_config in profile.devices:
        capabilities = [
            DeviceCapability(
                name=capability.name,
                kind=capability.kind,
                parameters=_deep_copy_dict(capability.parameters),
                constraints=capability.constraints.copy(),
                availability_policy=capability.availability_policy.copy(),
            )
            for capability in device_config.capabilities
        ]
        devices.append(
            Device(
                id=device_config.id,
                name=device_config.name,
                type=device_config.type,
                capabilities=capabilities,
                state=DeviceState(status="unknown"),
                metadata=device_config.metadata.copy(),
            )
        )
    return devices


def build_http_bindings(profile):
    """Materialize declarative HTTP bindings from a validated RuntimeProfile."""
    _ensure_profile(profile)
    return [
        HttpDeviceBinding(
            device_id=binding.device_id,
            base_url=binding.base_url,
            timeout_seconds=binding.timeout_seconds,
            read_path=binding.read_path,
            apply_path=binding.apply_path,
        )
        for binding in profile.http_bindings
    ]


def build_mqtt_bindings(profile):
    """Materialize declarative MQTT bindings from a validated RuntimeProfile."""
    _ensure_profile(profile)
    return [
        MQTTDeviceBinding(
            device_id=binding.device_id,
            request_topic=binding.request_topic,
            response_topic=binding.response_topic,
            timeout_seconds=binding.timeout_seconds,
            allowed_capabilities=binding.allowed_capabilities,
            allowed_response_keys=binding.allowed_response_keys,
        )
        for binding in profile.mqtt_bindings
    ]


def _ensure_profile(profile):
    if not isinstance(profile, RuntimeProfile):
        raise TypeError("expected RuntimeProfile")


def _is_non_empty_string(value):
    return isinstance(value, str) and bool(value)


def _is_valid_local_path_string(value):
    if not _is_non_empty_string(value):
        return False
    if "\x00" in value:
        return False
    if value.startswith("~"):
        return False
    if "://" in value or value.lower().startswith("file:"):
        return False
    if "$" in value or "%" in value:
        return False
    return True


def _parse_device_metadata(metadata):
    if not metadata:
        return {}
    if set(metadata.keys()) != {"room"}:
        raise ConfigurationError(CONFIG_INVALID)
    value = metadata["room"]
    if not isinstance(value, str):
        raise ConfigurationError(CONFIG_INVALID)
    if not value.strip():
        return {}
    room = room_label(value)
    if room is None:
        raise ConfigurationError(CONFIG_INVALID)
    return {"room": room}


def _require_exact_fields(payload, allowed, code):
    if set(payload.keys()) != allowed:
        raise ConfigurationError(code)


def _require_allowed_fields(payload, allowed, code):
    if not set(payload.keys()).issubset(allowed):
        raise ConfigurationError(code)


def _require_required_allowed_fields(payload, required, allowed, code):
    keys = set(payload.keys())
    if not required.issubset(keys):
        raise ConfigurationError(code)
    if not keys.issubset(allowed):
        raise ConfigurationError(code)


def _string_tuple(values):
    if not isinstance(values, list):
        raise ValueError("expected list")
    return tuple(values)


def _deep_copy_dict(value):
    return json.loads(json.dumps(value))

