"""Experimental driver boundary validation tools for JarvisOS."""

from dataclasses import dataclass, field

from jarvis_core.devices import Device, DeviceCapability


DRIVER_UNAVAILABLE = "driver_unavailable"
INVALID_DEVICE = "invalid_device"
CAPABILITY_NOT_FOUND = "capability_not_found"
INVALID_CAPABILITY_KIND = "invalid_capability_kind"
INVALID_PARAMETERS = "invalid_parameters"
SIMULATED_FAILURE = "simulated_failure"
SIMULATED_TIMEOUT = "simulated_timeout"
CONFIGURATION_INVALID = "configuration_invalid"
CONNECTION_FAILED = "connection_failed"
REQUEST_TIMEOUT = "request_timeout"
PROTOCOL_ERROR = "protocol_error"
INVALID_RESPONSE = "invalid_response"
AUTHENTICATION_FAILED = "authentication_failed"
OPERATION_NOT_SUPPORTED = "operation_not_supported"


@dataclass
class DriverResult:
    """Internal result for experimental driver-boundary operations.

    ``mutation_uncertain`` is a bounded, transport-neutral signal only
    consulted for failed ``apply`` results: True means the physical mutation
    outcome is uncertain (the device command may have been dispatched);
    False means the failure provably happened before any device command
    could have been sent.
    """

    success: bool
    observations: dict = field(default_factory=dict)
    error: str = None
    mutation_uncertain: bool = True

    def __post_init__(self):
        if not isinstance(self.success, bool):
            raise ValueError("DriverResult success must be a bool")
        if not isinstance(self.observations, dict):
            raise ValueError("DriverResult observations must be a dict")
        if self.error is not None and (
            not isinstance(self.error, str) or not self.error
        ):
            raise ValueError("DriverResult error must be None or a non-empty string")
        if not isinstance(self.mutation_uncertain, bool):
            raise ValueError("DriverResult mutation_uncertain must be a bool")


class SimulatedDriver:
    """Experimental in-memory validation artifact for the Driver Boundary."""

    def __init__(self, available=True):
        if not isinstance(available, bool):
            raise ValueError("SimulatedDriver available must be a bool")
        self._available = available
        self._readings = {}
        self._failures = {}

    def set_available(self, available):
        if not isinstance(available, bool):
            raise ValueError("SimulatedDriver available must be a bool")
        self._available = available

    def set_reading(self, device_id, capability_name, observations):
        if not isinstance(device_id, str) or not device_id:
            raise ValueError("device_id must be a non-empty string")
        if not isinstance(capability_name, str) or not capability_name:
            raise ValueError("capability_name must be a non-empty string")
        if not isinstance(observations, dict):
            raise ValueError("observations must be a dict")
        self._readings[(device_id, capability_name)] = observations.copy()

    def simulate_failure(self, operation, capability_name=None, error=SIMULATED_FAILURE):
        self._set_failure(operation, capability_name, error)

    def simulate_timeout(self, operation, capability_name=None):
        self._set_failure(operation, capability_name, SIMULATED_TIMEOUT)

    def clear_failures(self):
        self._failures.clear()

    def is_available(self, device):
        return isinstance(device, Device) and self._available

    def read(self, device, capability_name):
        capability, error = self._validate_capability(device, capability_name, "reading")
        if error:
            return DriverResult(False, {}, error)
        failure = self._configured_failure("read", capability.name)
        if failure:
            return DriverResult(False, {}, failure)
        observations = self._readings.get(
            (device.id, capability.name),
            {"capability": capability.name},
        )
        return DriverResult(True, observations.copy(), None)

    def apply(self, device, capability_name, parameters):
        if not isinstance(parameters, dict):
            return DriverResult(False, {}, INVALID_PARAMETERS)
        capability, error = self._validate_capability(device, capability_name, "action")
        if error:
            return DriverResult(False, {}, error)
        failure = self._configured_failure("apply", capability.name)
        if failure:
            return DriverResult(False, {}, failure)
        return DriverResult(
            True,
            {
                "applied": True,
                "capability": capability.name,
                "parameters": parameters.copy(),
            },
            None,
        )

    def _validate_capability(self, device, capability_name, expected_kind):
        if not isinstance(device, Device):
            return None, INVALID_DEVICE
        if not self.is_available(device):
            return None, DRIVER_UNAVAILABLE
        capability = self._find_capability(device, capability_name)
        if capability is None:
            return None, CAPABILITY_NOT_FOUND
        if capability.kind != expected_kind:
            return None, INVALID_CAPABILITY_KIND
        return capability, None

    def _find_capability(self, device, capability_name):
        if not isinstance(capability_name, str) or not capability_name:
            return None
        for capability in device.capabilities:
            if (
                isinstance(capability, DeviceCapability)
                and capability.name == capability_name
            ):
                return capability
        return None

    def _set_failure(self, operation, capability_name, error):
        if operation not in {"read", "apply"}:
            raise ValueError("operation must be read or apply")
        if capability_name is not None and (
            not isinstance(capability_name, str) or not capability_name
        ):
            raise ValueError("capability_name must be None or a non-empty string")
        if not isinstance(error, str) or not error:
            raise ValueError("error must be a non-empty string")
        self._failures[(operation, capability_name)] = error

    def _configured_failure(self, operation, capability_name):
        return self._failures.get((operation, capability_name)) or self._failures.get(
            (operation, None)
        )
