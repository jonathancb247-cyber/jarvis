from jarvis_core.domain import Command


DEVICE_NAMESPACE = "device"
DEVICE_EXECUTE_COMMAND = "device.execute"
READ_OPERATION = "read"
APPLY_OPERATION = "apply"
VALID_DEVICE_OPERATIONS = {READ_OPERATION, APPLY_OPERATION}
INVALID_DEVICE_INPUT_REASON = "invalid_device_command_input"


class Planner:
    def plan(self, text, source="cli"):
        normalized = text.strip().lower()
        if normalized.startswith(DEVICE_NAMESPACE):
            device_command = self._plan_device_command(text, source)
            if device_command is not None:
                return device_command
        if "time" in normalized or "hora" in normalized:
            return Command(name="time.now", args={}, source=source)
        return Command(name="unknown", args={"text": text}, source=source)

    def _plan_device_command(self, text, source):
        parts = text.strip().split()
        if len(parts) < 4:
            return self._invalid_device_input(source)
        namespace, operation, device_id, capability = parts[:4]
        if namespace.lower() != DEVICE_NAMESPACE:
            return None
        operation = operation.lower()
        if operation not in VALID_DEVICE_OPERATIONS:
            return self._invalid_device_input(source)
        if not device_id or not capability:
            return self._invalid_device_input(source)

        parameter_tokens = parts[4:]
        if operation == READ_OPERATION and parameter_tokens:
            return self._invalid_device_input(source)

        parameters = {}
        if operation == APPLY_OPERATION:
            parameters = self._parse_parameters(parameter_tokens)
            if parameters is None:
                return self._invalid_device_input(source)

        return Command(
            name=DEVICE_EXECUTE_COMMAND,
            args={
                "device_id": device_id,
                "capability": capability,
                "operation": operation,
                "parameters": parameters,
            },
            source=source,
        )

    def _parse_parameters(self, tokens):
        parameters = {}
        for token in tokens:
            if "=" not in token:
                return None
            key, value = token.split("=", 1)
            if not key or not value:
                return None
            if key in parameters:
                return None
            parameters[key] = value
        return parameters

    def _invalid_device_input(self, source):
        return Command(
            name="unknown",
            args={"reason": INVALID_DEVICE_INPUT_REASON},
            source=source,
        )
