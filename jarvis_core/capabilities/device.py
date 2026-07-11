"""Runtime capability bridge for Device Platform command execution."""

from jarvis_core.device_routing import (
    CAPABILITY_NOT_FOUND_ERROR,
    DEVICE_EXECUTE_COMMAND,
    DEVICE_NOT_FOUND,
    DRIVER_FAILURE,
    DRIVER_UNAVAILABLE_ERROR,
    INVALID_CAPABILITY_KIND_ERROR,
    INVALID_COMMAND,
    INVALID_COMMAND_ARGS,
    INVALID_DRIVER_RESULT,
    INVALID_PARAMETERS_ERROR,
    SIMULATED_TIMEOUT_ERROR,
    STATE_UPDATE_FAILED,
    DeviceExecutionResult,
)
from jarvis_core.domain import CapabilityResult, Command


INVALID_DEVICE_COMMAND = "invalid_device_command"
DEVICE_EXECUTION_FAILED = "device_execution_failed"
DEVICE_TIMEOUT = "device_timeout"


class DeviceRuntimeCapability:
    """Delegates device commands to DeviceCommandRouter."""

    name = DEVICE_EXECUTE_COMMAND

    def __init__(self, router):
        if not callable(getattr(router, "route", None)):
            raise TypeError("DeviceRuntimeCapability expects a router with route(command)")
        self.router = router

    def run(self, command, context):
        """Execute a device command and return a safe CapabilityResult."""
        if not isinstance(command, Command) or command.name != self.name:
            return self._failure(
                INVALID_DEVICE_COMMAND,
                "Device command is invalid.",
                self._command_data(command),
            )

        result = self.router.route(command)
        if not isinstance(result, DeviceExecutionResult):
            return self._failure(
                DEVICE_EXECUTION_FAILED,
                "Device command failed.",
                self._command_data(command),
            )

        data = self._result_data(result)
        if result.success:
            return CapabilityResult(
                success=True,
                message=self._success_message(result),
                data=data,
                error=None,
            )

        error = self._safe_error(result.error)
        return CapabilityResult(
            success=False,
            message=self._error_message(error),
            data=data,
            error=error,
        )

    def _success_message(self, result):
        if result.operation == "read":
            return "Device reading completed."
        if result.operation == "apply":
            return "Device action completed."
        return "Device command completed."

    def _error_message(self, error):
        messages = {
            DEVICE_NOT_FOUND: "Device not found.",
            CAPABILITY_NOT_FOUND_ERROR: "Device capability not found.",
            INVALID_DEVICE_COMMAND: "Device command is invalid.",
            INVALID_CAPABILITY_KIND_ERROR: "Device command is invalid.",
            INVALID_PARAMETERS_ERROR: "Device command is invalid.",
            DRIVER_UNAVAILABLE_ERROR: "Device is unavailable.",
            DEVICE_TIMEOUT: "Device command failed.",
            STATE_UPDATE_FAILED: "Device state could not be updated.",
            DEVICE_EXECUTION_FAILED: "Device command failed.",
        }
        return messages.get(error, "Device command failed.")

    def _safe_error(self, error):
        if error in {INVALID_COMMAND, INVALID_COMMAND_ARGS}:
            return INVALID_DEVICE_COMMAND
        if error == SIMULATED_TIMEOUT_ERROR:
            return DEVICE_TIMEOUT
        if error in {
            DEVICE_NOT_FOUND,
            CAPABILITY_NOT_FOUND_ERROR,
            INVALID_CAPABILITY_KIND_ERROR,
            INVALID_PARAMETERS_ERROR,
            DRIVER_UNAVAILABLE_ERROR,
            STATE_UPDATE_FAILED,
        }:
            return error
        if error in {DRIVER_FAILURE, INVALID_DRIVER_RESULT}:
            return DEVICE_EXECUTION_FAILED
        return DEVICE_EXECUTION_FAILED

    def _result_data(self, result):
        data = {
            "device_id": result.device_id,
            "capability": result.capability,
            "operation": result.operation,
        }
        if result.state is not None:
            data["state"] = {
                "status": result.state.status,
                "properties": result.state.properties.copy(),
            }
        return data

    def _command_data(self, command):
        if isinstance(command, Command):
            return {
                "command": command.name,
                "source": command.source,
            }
        return {"command": "unknown", "source": "unknown"}

    def _failure(self, error, message, data):
        return CapabilityResult(
            success=False,
            message=message,
            data=data,
            error=error,
        )
