from jarvis_core.domain import Command


DEVICE_NAMESPACE = "device"
DEVICE_CATALOG_COMMAND = "device.catalog"
DEVICE_DISCOVERY_COMMAND = "device.discovery"
DEVICE_EXECUTE_COMMAND = "device.execute"
DEVICE_LIFECYCLE_COMMAND = "device.lifecycle"
DEVICE_ONBOARDING_COMMAND = "device.onboarding"
READ_OPERATION = "read"
APPLY_OPERATION = "apply"
ADD_OPERATION = "add"
REMOVE_OPERATION = "remove"
DISCOVER_OPERATION = "discover"
ONBOARD_OPERATION = "onboard"
APPROVE_OPERATION = "approve"
SCAN_OPERATION = "scan"
LIST_OPERATION = "list"
INFO_OPERATION = "info"
CAPABILITIES_OPERATION = "capabilities"
STATE_OPERATION = "state"
VALID_DEVICE_OPERATIONS = {READ_OPERATION, APPLY_OPERATION}
VALID_LIFECYCLE_OPERATIONS = {ADD_OPERATION, REMOVE_OPERATION}
VALID_CATALOG_OPERATIONS = {
    LIST_OPERATION,
    INFO_OPERATION,
    CAPABILITIES_OPERATION,
    STATE_OPERATION,
}
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
        discovery_command = self._plan_device_discovery_command(parts, source)
        if discovery_command is not None:
            return discovery_command

        onboarding_command = self._plan_device_onboarding_command(parts, source)
        if onboarding_command is not None:
            return onboarding_command

        lifecycle_command = self._plan_device_lifecycle_command(parts, source)
        if lifecycle_command is not None:
            return lifecycle_command

        catalog_command = self._plan_device_catalog_command(parts, source)
        if catalog_command is not None:
            return catalog_command

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

    def _plan_device_lifecycle_command(self, parts, source):
        if not parts or parts[0].lower() != DEVICE_NAMESPACE:
            return None
        if len(parts) < 2:
            return None

        operation = parts[1].lower()
        if operation not in VALID_LIFECYCLE_OPERATIONS:
            return None

        if operation == REMOVE_OPERATION:
            if len(parts) != 3 or not parts[2]:
                return self._invalid_device_input(source)
            return Command(
                name=DEVICE_LIFECYCLE_COMMAND,
                args={
                    "operation": operation,
                    "device_id": parts[2],
                },
                source=source,
            )

        if len(parts) != 5 or not parts[2]:
            return self._invalid_device_input(source)

        parameters = self._parse_parameters(parts[3:])
        if parameters is None:
            return self._invalid_device_input(source)
        if set(parameters.keys()) != {"name", "type"}:
            return self._invalid_device_input(source)

        return Command(
            name=DEVICE_LIFECYCLE_COMMAND,
            args={
                "operation": operation,
                "device_id": parts[2],
                "name": parameters["name"],
                "type": parameters["type"],
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

    def _plan_device_discovery_command(self, parts, source):
        if not parts or parts[0].lower() != DEVICE_NAMESPACE:
            return None
        if len(parts) < 2:
            return None

        operation = parts[1].lower()
        if operation != DISCOVER_OPERATION:
            return None
        if len(parts) != 2:
            return self._invalid_device_input(source)

        return Command(
            name=DEVICE_DISCOVERY_COMMAND,
            args={"operation": SCAN_OPERATION},
            source=source,
        )

    def _plan_device_onboarding_command(self, parts, source):
        if not parts or parts[0].lower() != DEVICE_NAMESPACE:
            return None
        if len(parts) < 2:
            return None

        operation = parts[1].lower()
        if operation != ONBOARD_OPERATION:
            return None
        if len(parts) != 5:
            return self._invalid_device_input(source)

        candidate_id = parts[2]
        keyword = parts[3].lower()
        device_id = parts[4]
        if not candidate_id or keyword != "as" or not device_id:
            return self._invalid_device_input(source)

        return Command(
            name=DEVICE_ONBOARDING_COMMAND,
            args={
                "operation": APPROVE_OPERATION,
                "candidate_id": candidate_id,
                "device_id": device_id,
            },
            source=source,
        )

    def _invalid_device_input(self, source):
        return Command(
            name="unknown",
            args={"reason": INVALID_DEVICE_INPUT_REASON},
            source=source,
        )

    def _plan_device_catalog_command(self, parts, source):
        if not parts or parts[0].lower() != DEVICE_NAMESPACE:
            return None
        if len(parts) < 2:
            return None

        operation = parts[1].lower()
        if operation not in VALID_CATALOG_OPERATIONS:
            return None

        if operation == LIST_OPERATION:
            if len(parts) != 2:
                return self._invalid_device_input(source)
            return Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": operation},
                source=source,
            )

        if len(parts) != 3:
            return self._invalid_device_input(source)

        return Command(
            name=DEVICE_CATALOG_COMMAND,
            args={
                "operation": operation,
                "device_id": parts[2],
            },
            source=source,
        )
