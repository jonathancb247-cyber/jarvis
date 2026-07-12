"""Runtime capability for read-only DeviceRegistry catalog inspection."""

from jarvis_core.devices import DeviceCapability, DeviceRegistry
from jarvis_core.domain import CapabilityResult, Command


DEVICE_CATALOG_COMMAND = "device.catalog"
LIST_OPERATION = "list"
INFO_OPERATION = "info"
CAPABILITIES_OPERATION = "capabilities"
STATE_OPERATION = "state"
VALID_OPERATIONS = {
    LIST_OPERATION,
    INFO_OPERATION,
    CAPABILITIES_OPERATION,
    STATE_OPERATION,
}

INVALID_DEVICE_CATALOG_COMMAND = "invalid_device_catalog_command"
DEVICE_NOT_FOUND = "device_not_found"
DEVICE_REGISTRY_UNAVAILABLE = "device_registry_unavailable"
UNSUPPORTED_DEVICE_CATALOG_OPERATION = "unsupported_device_catalog_operation"


class DeviceCatalogCapability:
    """Read-only Runtime Capability for DeviceRegistry inspection."""

    name = DEVICE_CATALOG_COMMAND

    def run(self, command, context):
        """Execute a read-only device catalog query."""
        if not isinstance(command, Command) or command.name != self.name:
            return self._failure(
                INVALID_DEVICE_CATALOG_COMMAND,
                "Device catalog command is invalid.",
                {},
            )

        registry = getattr(context, "device_registry", None)
        if not isinstance(registry, DeviceRegistry):
            return self._failure(
                DEVICE_REGISTRY_UNAVAILABLE,
                "Device registry is unavailable.",
                self._command_data(command),
            )

        operation = command.args.get("operation")
        if operation not in VALID_OPERATIONS:
            return self._failure(
                UNSUPPORTED_DEVICE_CATALOG_OPERATION,
                "Device catalog command is invalid.",
                self._command_data(command),
            )

        if operation == LIST_OPERATION:
            return self._list_devices(registry)

        device_id = command.args.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            return self._failure(
                INVALID_DEVICE_CATALOG_COMMAND,
                "Device catalog command is invalid.",
                {"operation": operation},
            )

        try:
            device = registry.get(device_id)
        except KeyError:
            return self._failure(
                DEVICE_NOT_FOUND,
                "Device not found.",
                {"operation": operation, "device_id": device_id},
            )

        if operation == INFO_OPERATION:
            return self._device_info(device)
        if operation == CAPABILITIES_OPERATION:
            return self._device_capabilities(device)
        return self._device_state(device)

    def _list_devices(self, registry):
        devices = [self._device_summary(device) for device in registry.list()]
        count = len(devices)
        if count == 0:
            message = "No devices registered."
        else:
            labels = [
                f"{device['id']} ({device['type']}, {device['status']})"
                for device in devices
            ]
            message = "Devices: " + ", ".join(labels) + "."
        return CapabilityResult(
            success=True,
            message=message,
            data={"count": count, "devices": devices},
            error=None,
        )

    def _device_info(self, device):
        summary = self._device_summary(device)
        return CapabilityResult(
            success=True,
            message=(
                f"Device {device.id}: {device.name}, type {device.type}, "
                f"status {device.state.status}."
            ),
            data={"device": summary},
            error=None,
        )

    def _device_capabilities(self, device):
        formal, legacy = self._capability_data(device)
        message = self._capability_message(device.id, formal, legacy)
        return CapabilityResult(
            success=True,
            message=message,
            data={
                "device_id": device.id,
                "formal": formal,
                "legacy": legacy,
            },
            error=None,
        )

    def _device_state(self, device):
        state = {
            "status": device.state.status,
            "properties": device.state.properties.copy(),
            "updated_at": device.state.updated_at,
        }
        return CapabilityResult(
            success=True,
            message=f"Device {device.id} state: {device.state.status}.",
            data={"device_id": device.id, "state": state},
            error=None,
        )

    def _device_summary(self, device):
        formal, legacy = self._capability_data(device)
        return {
            "id": device.id,
            "name": device.name,
            "type": device.type,
            "status": device.state.status,
            "formal_capability_count": len(formal),
            "legacy_capability_count": len(legacy),
        }

    def _capability_data(self, device):
        formal = []
        legacy = []
        for capability in device.capabilities:
            if isinstance(capability, DeviceCapability):
                formal.append(
                    {
                        "name": capability.name,
                        "kind": capability.kind,
                        "parameters": capability.parameters.copy(),
                        "constraints": capability.constraints.copy(),
                        "availability_policy": capability.availability_policy.copy(),
                    }
                )
            elif isinstance(capability, str):
                legacy.append(capability)
        return formal, legacy

    def _capability_message(self, device_id, formal, legacy):
        if not formal and not legacy:
            return f"Device {device_id} has no capabilities."
        parts = []
        if formal:
            formal_labels = [
                f"{capability['name']} ({capability['kind']})"
                for capability in formal
            ]
            parts.append("formal: " + ", ".join(formal_labels))
        if legacy:
            parts.append("legacy: " + ", ".join(legacy))
        return f"Device {device_id} capabilities: " + "; ".join(parts) + "."

    def _command_data(self, command):
        return {
            "command": command.name,
            "source": command.source,
        }

    def _failure(self, error, message, data):
        return CapabilityResult(
            success=False,
            message=message,
            data=data,
            error=error,
        )
