"""Device command routing boundary for JarvisOS."""

from dataclasses import dataclass, field

from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.domain import Command
from jarvis_core.drivers import (
    CAPABILITY_NOT_FOUND,
    DRIVER_UNAVAILABLE,
    INVALID_CAPABILITY_KIND,
    INVALID_PARAMETERS,
    SIMULATED_TIMEOUT,
    DriverResult,
)


DEVICE_EXECUTE_COMMAND = "device.execute"
READ_OPERATION = "read"
APPLY_OPERATION = "apply"
VALID_OPERATIONS = {READ_OPERATION, APPLY_OPERATION}

INVALID_COMMAND = "invalid_command"
INVALID_COMMAND_ARGS = "invalid_command_args"
DEVICE_NOT_FOUND = "device_not_found"
CAPABILITY_NOT_FOUND_ERROR = "capability_not_found"
INVALID_CAPABILITY_KIND_ERROR = "invalid_capability_kind"
INVALID_PARAMETERS_ERROR = "invalid_parameters"
DRIVER_UNAVAILABLE_ERROR = "driver_unavailable"
DRIVER_FAILURE = "driver_failure"
SIMULATED_TIMEOUT_ERROR = "simulated_timeout"
INVALID_DRIVER_RESULT = "invalid_driver_result"
STATE_UPDATE_FAILED = "state_update_failed"

UNKNOWN_DEVICE_ID = "unknown"
UNKNOWN_CAPABILITY = "unknown"
DEFAULT_OPERATION = READ_OPERATION


@dataclass
class DeviceExecutionResult:
    """Internal Device Platform result for device command routing."""

    success: bool
    device_id: str
    capability: str
    operation: str
    state: DeviceState = None
    error: str = None
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.success, bool):
            raise ValueError("DeviceExecutionResult success must be a bool")
        if not isinstance(self.device_id, str) or not self.device_id:
            raise ValueError(
                "DeviceExecutionResult device_id must be a non-empty string"
            )
        if not isinstance(self.capability, str) or not self.capability:
            raise ValueError(
                "DeviceExecutionResult capability must be a non-empty string"
            )
        if self.operation not in VALID_OPERATIONS:
            raise ValueError("DeviceExecutionResult operation must be read or apply")
        if self.state is not None and not isinstance(self.state, DeviceState):
            raise ValueError("DeviceExecutionResult state must be None or DeviceState")
        if self.error is not None and (
            not isinstance(self.error, str) or not self.error
        ):
            raise ValueError(
                "DeviceExecutionResult error must be None or a non-empty string"
            )
        if not isinstance(self.data, dict):
            raise ValueError("DeviceExecutionResult data must be a dict")


class DeviceCommandRouter:
    """Routes approved device commands to driver operations."""

    def __init__(self, device_registry, driver, state_coordinator):
        if not isinstance(device_registry, DeviceRegistry):
            raise TypeError("DeviceCommandRouter expects a DeviceRegistry")
        if not callable(getattr(driver, "read", None)):
            raise TypeError("DeviceCommandRouter driver must define read")
        if not callable(getattr(driver, "apply", None)):
            raise TypeError("DeviceCommandRouter driver must define apply")
        if not isinstance(state_coordinator, DeviceStateCoordinator):
            raise TypeError("DeviceCommandRouter expects a DeviceStateCoordinator")

        self.device_registry = device_registry
        self.driver = driver
        self.state_coordinator = state_coordinator

    def route(self, command):
        """Route a device command and return an internal DeviceExecutionResult."""
        if not isinstance(command, Command):
            return self._failure(
                UNKNOWN_DEVICE_ID,
                UNKNOWN_CAPABILITY,
                DEFAULT_OPERATION,
                INVALID_COMMAND,
            )
        if command.name != DEVICE_EXECUTE_COMMAND:
            return self._failure(
                UNKNOWN_DEVICE_ID,
                UNKNOWN_CAPABILITY,
                DEFAULT_OPERATION,
                INVALID_COMMAND,
            )

        parsed = self._parse_args(command.args)
        if parsed["error"]:
            return self._failure(
                parsed["device_id"],
                parsed["capability"],
                parsed["operation"],
                parsed["error"],
            )

        device_id = parsed["device_id"]
        capability_name = parsed["capability"]
        operation = parsed["operation"]
        parameters = parsed["parameters"]

        try:
            device = self.device_registry.get(device_id)
        except KeyError:
            return self._failure(
                device_id,
                capability_name,
                operation,
                DEVICE_NOT_FOUND,
            )

        capability = self._find_capability(device, capability_name)
        if capability is None:
            return self._failure(
                device_id,
                capability_name,
                operation,
                CAPABILITY_NOT_FOUND_ERROR,
            )

        expected_kind = "reading" if operation == READ_OPERATION else "action"
        if capability.kind != expected_kind:
            return self._failure(
                device_id,
                capability_name,
                operation,
                INVALID_CAPABILITY_KIND_ERROR,
            )

        driver_result = self._call_driver(device, capability_name, operation, parameters)
        if not isinstance(driver_result, DriverResult):
            return self._failure(
                device_id,
                capability_name,
                operation,
                INVALID_DRIVER_RESULT,
            )

        if not driver_result.success:
            state, state_error = self._coordinate_state(
                device,
                capability_name,
                operation,
                driver_result,
            )
            if state_error:
                return self._failure(
                    device_id,
                    capability_name,
                    operation,
                    state_error,
                )
            return DeviceExecutionResult(
                success=False,
                device_id=device_id,
                capability=capability_name,
                operation=operation,
                state=state,
                error=self._map_driver_error(driver_result.error),
                data=self._safe_data(device_id, capability_name, operation),
            )

        state, state_error = self._coordinate_state(
            device,
            capability_name,
            operation,
            driver_result,
        )
        if state_error:
            return self._failure(
                device_id,
                capability_name,
                operation,
                state_error,
            )
        return DeviceExecutionResult(
            success=True,
            device_id=device_id,
            capability=capability_name,
            operation=operation,
            state=state,
            error=None,
            data=self._safe_data(device_id, capability_name, operation),
        )

    def _parse_args(self, args):
        device_id = args.get("device_id")
        capability = args.get("capability")
        operation = args.get("operation")
        parameters = args.get("parameters", {})

        safe_device_id = (
            device_id
            if isinstance(device_id, str) and device_id
            else UNKNOWN_DEVICE_ID
        )
        safe_capability = (
            capability
            if isinstance(capability, str) and capability
            else UNKNOWN_CAPABILITY
        )
        safe_operation = operation if operation in VALID_OPERATIONS else DEFAULT_OPERATION

        if not isinstance(device_id, str) or not device_id:
            return self._parsed_args(
                safe_device_id,
                safe_capability,
                safe_operation,
                {},
                INVALID_COMMAND_ARGS,
            )
        if not isinstance(capability, str) or not capability:
            return self._parsed_args(
                safe_device_id,
                safe_capability,
                safe_operation,
                {},
                INVALID_COMMAND_ARGS,
            )
        if operation not in VALID_OPERATIONS:
            return self._parsed_args(
                safe_device_id,
                safe_capability,
                safe_operation,
                {},
                INVALID_COMMAND_ARGS,
            )
        if not isinstance(parameters, dict):
            return self._parsed_args(
                safe_device_id,
                safe_capability,
                safe_operation,
                {},
                INVALID_PARAMETERS_ERROR,
            )
        return self._parsed_args(device_id, capability, operation, parameters, None)

    def _parsed_args(self, device_id, capability, operation, parameters, error):
        return {
            "device_id": device_id,
            "capability": capability,
            "operation": operation,
            "parameters": parameters,
            "error": error,
        }

    def _find_capability(self, device, capability_name):
        for capability in device.capabilities:
            if (
                isinstance(capability, DeviceCapability)
                and capability.name == capability_name
            ):
                return capability
        return None

    def _call_driver(self, device, capability_name, operation, parameters):
        if operation == READ_OPERATION:
            return self.driver.read(device, capability_name)
        return self.driver.apply(device, capability_name, parameters)

    def _coordinate_state(self, device, capability_name, operation, driver_result):
        try:
            state = self.state_coordinator.coordinate(
                device,
                capability_name,
                operation,
                driver_result,
                self.device_registry,
            )
            return state, None
        except Exception:
            return device.state, STATE_UPDATE_FAILED

    def _map_driver_error(self, error):
        if error == DRIVER_UNAVAILABLE:
            return DRIVER_UNAVAILABLE_ERROR
        if error == CAPABILITY_NOT_FOUND:
            return CAPABILITY_NOT_FOUND_ERROR
        if error == INVALID_CAPABILITY_KIND:
            return INVALID_CAPABILITY_KIND_ERROR
        if error == INVALID_PARAMETERS:
            return INVALID_PARAMETERS_ERROR
        if error == SIMULATED_TIMEOUT:
            return SIMULATED_TIMEOUT_ERROR
        return DRIVER_FAILURE

    def _failure(self, device_id, capability, operation, error):
        return DeviceExecutionResult(
            success=False,
            device_id=device_id,
            capability=capability,
            operation=operation,
            state=None,
            error=error,
            data=self._safe_data(device_id, capability, operation),
        )

    def _safe_data(self, device_id, capability, operation):
        return {
            "device_id": device_id,
            "capability": capability,
            "operation": operation,
        }
