"""Internal device model for JarvisOS AVP-001 Phase 1.3."""

from dataclasses import dataclass, field


DEVICE_CAPABILITY_KINDS = {"action", "reading"}


@dataclass
class DeviceCapability:
    """Domain descriptor for what a device supports."""

    name: str
    kind: str
    parameters: dict = field(default_factory=dict)
    constraints: dict = field(default_factory=dict)
    availability_policy: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("DeviceCapability name must be a non-empty string")
        if self.kind not in DEVICE_CAPABILITY_KINDS:
            raise ValueError("DeviceCapability kind must be action or reading")
        if not isinstance(self.parameters, dict):
            raise ValueError("DeviceCapability parameters must be a dict")
        for parameter_name, descriptor in self.parameters.items():
            if not isinstance(parameter_name, str) or not parameter_name:
                raise ValueError("DeviceCapability parameter names must be non-empty strings")
            if not isinstance(descriptor, dict):
                raise ValueError("DeviceCapability parameter descriptors must be dicts")
            if "required" in descriptor and not isinstance(descriptor["required"], bool):
                raise ValueError("DeviceCapability parameter required must be a bool")
            if "constraints" in descriptor and not isinstance(
                descriptor["constraints"], dict
            ):
                raise ValueError("DeviceCapability parameter constraints must be a dict")
            if "metadata" in descriptor and not isinstance(descriptor["metadata"], dict):
                raise ValueError("DeviceCapability parameter metadata must be a dict")
        if not isinstance(self.constraints, dict):
            raise ValueError("DeviceCapability constraints must be a dict")
        if not isinstance(self.availability_policy, dict):
            raise ValueError("DeviceCapability availability_policy must be a dict")
        if not isinstance(self.metadata, dict):
            raise ValueError("DeviceCapability metadata must be a dict")


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
        for capability in self.capabilities:
            if isinstance(capability, DeviceCapability):
                continue
            if isinstance(capability, str) and capability:
                continue
            raise ValueError(
                "Device capabilities must contain DeviceCapability or non-empty string descriptors"
            )
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
