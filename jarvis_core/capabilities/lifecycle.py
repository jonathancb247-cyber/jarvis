"""Runtime capability for minimal in-memory Device lifecycle mutations."""

from jarvis_core.devices import Device, DeviceRegistry, DeviceState
from jarvis_core.domain import CapabilityResult, Command


DEVICE_LIFECYCLE_COMMAND = "device.lifecycle"
ADD_OPERATION = "add"
REMOVE_OPERATION = "remove"
VALID_OPERATIONS = {ADD_OPERATION, REMOVE_OPERATION}

INVALID_DEVICE_LIFECYCLE_COMMAND = "invalid_device_lifecycle_command"
DEVICE_ALREADY_EXISTS = "device_already_exists"
DEVICE_NOT_FOUND = "device_not_found"
DEVICE_REGISTRY_UNAVAILABLE = "device_registry_unavailable"
DEVICE_LIFECYCLE_FAILED = "device_lifecycle_failed"


class DeviceLifecycleRegistrar:
    """Internal primitive that applies lifecycle registration invariants."""

    def register(self, registry, device):
        if not isinstance(registry, DeviceRegistry):
            raise TypeError("DeviceLifecycleRegistrar expects a DeviceRegistry")
        if not isinstance(device, Device):
            raise TypeError("DeviceLifecycleRegistrar expects a Device")
        registry.register(device)
        return device


class DeviceLifecycleCapability:
    """Runtime Capability for adding and removing in-memory devices."""

    name = DEVICE_LIFECYCLE_COMMAND

    def __init__(self, registrar=None):
        self.registrar = registrar if registrar is not None else DeviceLifecycleRegistrar()

    def run(self, command, context):
        if not isinstance(command, Command) or command.name != self.name:
            return self._failure(
                INVALID_DEVICE_LIFECYCLE_COMMAND,
                "Device lifecycle command is invalid.",
                {},
            )

        registry = getattr(context, "device_registry", None)
        if not isinstance(registry, DeviceRegistry):
            return self._failure(
                DEVICE_REGISTRY_UNAVAILABLE,
                "Device registry is unavailable.",
                self._safe_command_data(command),
            )

        operation = command.args.get("operation")
        device_id = command.args.get("device_id")
        if operation not in VALID_OPERATIONS or not self._is_non_empty_string(device_id):
            return self._failure(
                INVALID_DEVICE_LIFECYCLE_COMMAND,
                "Device lifecycle command is invalid.",
                self._safe_command_data(command),
            )

        if operation == ADD_OPERATION:
            return self._add_device(command, registry)
        return self._remove_device(command, registry)

    def _add_device(self, command, registry):
        name = command.args.get("name")
        device_type = command.args.get("type")
        if not self._is_non_empty_string(name) or not self._is_non_empty_string(
            device_type
        ):
            return self._failure(
                INVALID_DEVICE_LIFECYCLE_COMMAND,
                "Device lifecycle command is invalid.",
                self._safe_command_data(command),
            )

        device_id = command.args["device_id"]
        device = Device(
            id=device_id,
            name=name,
            type=device_type,
            capabilities=[],
            state=DeviceState(status="unknown"),
            metadata={},
        )
        try:
            self.registrar.register(registry, device)
        except ValueError:
            return self._failure(
                DEVICE_ALREADY_EXISTS,
                "Device already exists.",
                self._safe_command_data(command),
            )
        except Exception:
            return self._failure(
                DEVICE_LIFECYCLE_FAILED,
                "Device lifecycle command is invalid.",
                self._safe_command_data(command),
            )

        return CapabilityResult(
            success=True,
            message="Device registered.",
            data=self._safe_command_data(command),
            error=None,
        )

    def _remove_device(self, command, registry):
        try:
            registry.unregister(command.args["device_id"])
        except KeyError:
            return self._failure(
                DEVICE_NOT_FOUND,
                "Device not found.",
                self._safe_command_data(command),
            )
        except Exception:
            return self._failure(
                DEVICE_LIFECYCLE_FAILED,
                "Device lifecycle command is invalid.",
                self._safe_command_data(command),
            )

        return CapabilityResult(
            success=True,
            message="Device removed.",
            data=self._safe_command_data(command),
            error=None,
        )

    def _safe_command_data(self, command):
        if not isinstance(command, Command):
            return {}
        data = {}
        operation = command.args.get("operation")
        device_id = command.args.get("device_id")
        if isinstance(operation, str) and operation:
            data["operation"] = operation
        if isinstance(device_id, str) and device_id:
            data["device_id"] = device_id
        return data

    def _failure(self, error, message, data):
        return CapabilityResult(
            success=False,
            message=message,
            data=data,
            error=error,
        )

    def _is_non_empty_string(self, value):
        return isinstance(value, str) and bool(value)
