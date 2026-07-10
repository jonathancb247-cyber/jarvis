"""Internal device model for JarvisOS AVP-001 Phase 1.3."""

from dataclasses import dataclass, field


@dataclass
class DeviceState:
    """Known state snapshot for an internal device model."""

    status: str = "unknown"
    properties: dict = field(default_factory=dict)
    updated_at: str = None

    def __post_init__(self):
        if not isinstance(self.status, str) or not self.status:
            raise ValueError("DeviceState status must be a non-empty string")
        if not isinstance(self.properties, dict):
            raise ValueError("DeviceState properties must be a dict")


@dataclass
class Device:
    """Internal model of something controllable or observable."""

    id: str
    name: str
    type: str
    capabilities: list = field(default_factory=list)
    state: DeviceState = field(default_factory=DeviceState)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("Device id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("Device name must be a non-empty string")
        if not isinstance(self.type, str) or not self.type:
            raise ValueError("Device type must be a non-empty string")
        if not isinstance(self.capabilities, list):
            raise ValueError("Device capabilities must be a list")
        if not isinstance(self.metadata, dict):
            raise ValueError("Device metadata must be a dict")


class DeviceRegistry:
    """Stores and looks up internal device models."""

    def __init__(self):
        self.devices = {}

    def register(self, device):
        if not isinstance(device, Device):
            raise TypeError("DeviceRegistry.register expects a Device")
        if device.id in self.devices:
            raise ValueError(f"Device already registered: {device.id}")
        self.devices[device.id] = device

    def get(self, device_id):
        if device_id not in self.devices:
            raise KeyError(f"Device not found: {device_id}")
        return self.devices[device_id]

    def list(self):
        return list(self.devices.values())

    def find_by_name(self, name):
        return [device for device in self.devices.values() if device.name == name]

    def find_by_type(self, device_type):
        return [device for device in self.devices.values() if device.type == device_type]

    def update_state(self, device_id, state):
        if not isinstance(state, DeviceState):
            raise TypeError("DeviceRegistry.update_state expects a DeviceState")
        device = self.get(device_id)
        device.state = state
        return device

    def has(self, device_id):
        return device_id in self.devices
