"""Detached safe read projections for the Runtime API adapter."""

from dataclasses import dataclass

from jarvis_core.devices import DeviceCapability, DeviceRegistry
from jarvis_core.api.validation import safe_string


MAX_DEVICES = 256
MAX_CAPABILITIES = 64
MAX_PROPERTIES = 64
SAFE_PROPERTY_TYPES = (str, int, float, bool, type(None))
FORBIDDEN_PROPERTY_TOKENS = (
    "url",
    "uri",
    "ip",
    "host",
    "port",
    "header",
    "token",
    "secret",
    "password",
    "credential",
    "payload",
    "error",
    "stack",
    "trace",
    "binding",
)


@dataclass(frozen=True)
class ApiHealthView:
    status: str
    prototype: str
    device_count: int
    persistence_enabled: bool
    profile_name: str = None

    def to_dict(self):
        payload = {
            "status": self.status,
            "prototype": self.prototype,
            "device_count": self.device_count,
            "persistence_enabled": self.persistence_enabled,
        }
        if self.profile_name:
            payload["profile_name"] = self.profile_name
        return payload


@dataclass(frozen=True)
class ApiCapabilityView:
    name: str
    kind: str
    parameters: dict

    def to_dict(self):
        return {
            "name": self.name,
            "kind": self.kind,
            "parameters": self.parameters,
        }


@dataclass(frozen=True)
class ApiDeviceStateView:
    status: str
    is_current: bool
    semantic_properties: dict
    updated_at: str = None

    def to_dict(self):
        return {
            "status": self.status,
            "is_current": self.is_current,
            "semantic_properties": self.semantic_properties,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ApiDeviceListItem:
    device_id: str
    name: str
    type: str
    status: str
    is_current: bool
    capability_count: int

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "is_current": self.is_current,
            "capability_count": self.capability_count,
        }


@dataclass(frozen=True)
class ApiDeviceDetail:
    device_id: str
    name: str
    type: str
    status: str
    is_current: bool
    capabilities: tuple
    semantic_properties: dict
    updated_at: str = None

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "is_current": self.is_current,
            "capabilities": [capability.to_dict() for capability in self.capabilities],
            "semantic_properties": self.semantic_properties,
            "updated_at": self.updated_at,
        }


class ApiProjectionBuilder:
    """Builds JSON-safe detached views from approved read-only dependencies."""

    def __init__(self, device_registry, profile_name=None, persistence_enabled=False):
        if not isinstance(device_registry, DeviceRegistry):
            raise TypeError("ApiProjectionBuilder requires a DeviceRegistry")
        self._device_registry = device_registry
        self._profile_name = profile_name
        self._persistence_enabled = bool(persistence_enabled)

    def health(self):
        return ApiHealthView(
            status="ok",
            prototype="AVP-001",
            device_count=len(self._safe_devices()),
            persistence_enabled=self._persistence_enabled,
            profile_name=safe_string(self._profile_name) if self._profile_name else None,
        )

    def device_list(self):
        return [
            self._device_list_item(device)
            for device in self._safe_devices()
        ]

    def device_detail(self, device_id):
        device = self._device_registry.get(device_id)
        state = self._state_view(device)
        return ApiDeviceDetail(
            device_id=safe_string(device.id),
            name=safe_string(device.name),
            type=safe_string(device.type),
            status=state.status,
            is_current=state.is_current,
            capabilities=tuple(self.capabilities(device_id)),
            semantic_properties=state.semantic_properties,
            updated_at=state.updated_at,
        )

    def capabilities(self, device_id):
        device = self._device_registry.get(device_id)
        views = []
        for capability in device.capabilities:
            if not isinstance(capability, DeviceCapability):
                continue
            views.append(self._capability_view(capability))
            if len(views) >= MAX_CAPABILITIES:
                break
        return views

    def device_state(self, device_id):
        return self._state_view(self._device_registry.get(device_id))

    def _safe_devices(self):
        devices = sorted(self._device_registry.list(), key=lambda device: device.id)
        return devices[:MAX_DEVICES]

    def _device_list_item(self, device):
        state = self._state_view(device)
        return ApiDeviceListItem(
            device_id=safe_string(device.id),
            name=safe_string(device.name),
            type=safe_string(device.type),
            status=state.status,
            is_current=state.is_current,
            capability_count=len(
                [capability for capability in device.capabilities if isinstance(capability, DeviceCapability)]
            ),
        )

    def _state_view(self, device):
        status = safe_string(device.state.status)
        return ApiDeviceStateView(
            status=status,
            is_current=status == "known",
            semantic_properties=self._semantic_properties(device.state.properties),
            updated_at=safe_string(device.state.updated_at) if device.state.updated_at else None,
        )

    def _capability_view(self, capability):
        return ApiCapabilityView(
            name=safe_string(capability.name),
            kind=safe_string(capability.kind),
            parameters=self._safe_parameters(capability.parameters),
        )

    def _safe_parameters(self, parameters):
        safe = {}
        for name, descriptor in sorted(parameters.items()):
            if not isinstance(name, str) or not isinstance(descriptor, dict):
                continue
            safe_descriptor = {}
            if isinstance(descriptor.get("type"), str):
                safe_descriptor["type"] = safe_string(descriptor["type"])
            if isinstance(descriptor.get("required"), bool):
                safe_descriptor["required"] = descriptor["required"]
            safe[safe_string(name)] = safe_descriptor
        return safe

    def _semantic_properties(self, properties):
        safe = {}
        for key, value in sorted(properties.items()):
            if len(safe) >= MAX_PROPERTIES:
                break
            if not isinstance(key, str) or _forbidden_property_name(key):
                continue
            if not isinstance(value, SAFE_PROPERTY_TYPES):
                continue
            safe[safe_string(key)] = safe_string(value) if isinstance(value, str) else value
        return safe


def _forbidden_property_name(name):
    lowered = name.lower()
    return any(token in lowered for token in FORBIDDEN_PROPERTY_TOKENS)
