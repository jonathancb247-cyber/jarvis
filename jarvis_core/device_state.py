"""Device state coordination boundary for JarvisOS."""

from datetime import datetime, timezone

from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.drivers import DRIVER_UNAVAILABLE, DriverResult


VALID_OPERATIONS = {"read", "apply"}
OPERATION_KINDS = {
    "read": "reading",
    "apply": "action",
}
TECHNICAL_OBSERVATION_KEYS = {
    "applied",
    "args",
    "capability",
    "error",
    "errors",
    "metadata",
    "parameters",
    "stack_trace",
    "traceback",
}


class DeviceStateCoordinator:
    """Transforms approved driver observations into official DeviceState."""

    def coordinate(self, device, capability_name, operation, driver_result, registry):
        if not isinstance(device, Device):
            raise TypeError("DeviceStateCoordinator expects a Device")
        if not isinstance(capability_name, str) or not capability_name:
            raise ValueError("capability_name must be a non-empty string")
        if operation not in VALID_OPERATIONS:
            raise ValueError("operation must be read or apply")
        if not isinstance(driver_result, DriverResult):
            raise TypeError("driver_result must be a DriverResult")
        if not isinstance(registry, DeviceRegistry):
            raise TypeError("registry must be a DeviceRegistry")

        capability = self._find_capability(device, capability_name)
        if capability is None:
            return device.state
        if capability.kind != OPERATION_KINDS[operation]:
            return device.state

        if not driver_result.success:
            if driver_result.error == DRIVER_UNAVAILABLE:
                return self._update_state(
                    device,
                    registry,
                    status="unavailable",
                    properties=device.state.properties.copy(),
                )
            if operation == "apply" and device.state.status == "known":
                # An uncertain mutation (timeout, transport failure, malformed
                # or mismatched acknowledgement) must NOT leave the previous
                # value represented as current truth. Retain the previous
                # semantic value and demote freshness without inventing a value;
                # a fresh validated acknowledgement restores status to "known".
                return self._update_state(
                    device,
                    registry,
                    status="stale",
                    properties=device.state.properties.copy(),
                )
            if operation == "read" and device.state.status == "known":
                return self._update_state(
                    device,
                    registry,
                    status="stale",
                    properties=device.state.properties.copy(),
                )
            return device.state

        approved_observations = self._approved_observations(
            driver_result.observations
        )
        if not approved_observations:
            return device.state

        properties = device.state.properties.copy()
        properties.update(approved_observations)
        return self._update_state(
            device,
            registry,
            status="known",
            properties=properties,
        )

    def _find_capability(self, device, capability_name):
        for capability in device.capabilities:
            if (
                isinstance(capability, DeviceCapability)
                and capability.name == capability_name
            ):
                return capability
        return None

    def _approved_observations(self, observations):
        return {
            key: value
            for key, value in observations.items()
            if key not in TECHNICAL_OBSERVATION_KEYS
        }

    def _update_state(self, device, registry, status, properties):
        state = DeviceState(
            status=status,
            properties=properties,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.update_state(device.id, state)
        return state
