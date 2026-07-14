"""Safe semantic context projection for the experimental AI Adapter."""

import re

from jarvis_core.ai.contracts import (
    MAX_CAPABILITIES_PER_DEVICE,
    MAX_CONTEXT_DEVICES,
    MAX_PROPERTIES_PER_DEVICE,
    MAX_SAFE_TEXT_LENGTH,
    PLAN_SCHEMA_VERSION,
    AISafeCapability,
    AISafeContext,
    AISafeDevice,
    AISafeDeviceState,
    AISafePolicyContext,
)
from jarvis_core.devices import DeviceCapability


SAFE_PROPERTY_NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
TECHNICAL_PROPERTY_NAMES = {
    "args",
    "binding",
    "bindings",
    "config",
    "credentials",
    "driver_result",
    "endpoint",
    "error",
    "errors",
    "exception",
    "headers",
    "host",
    "ip",
    "metadata",
    "password",
    "path",
    "payload",
    "port",
    "request",
    "response",
    "secret",
    "stack_trace",
    "timeout",
    "token",
    "traceback",
    "url",
}


class SafeContextBuilder:
    """Build detached, bounded, semantic snapshots for AI planning."""

    def build(self, user_request, device_registry, session_context=None):
        devices = []
        for device in device_registry.list()[:MAX_CONTEXT_DEVICES]:
            devices.append(self._project_device(device))
        return AISafeContext(
            schema_version=PLAN_SCHEMA_VERSION,
            user_request=_sanitize_text(user_request, MAX_SAFE_TEXT_LENGTH * 8),
            session_context=self._project_session_context(session_context or {}),
            devices=tuple(devices),
            command_grammar=command_grammar_catalog(),
            policies=AISafePolicyContext(),
            previous_results=(),
        )

    def _project_session_context(self, session_context):
        if not isinstance(session_context, dict):
            return ()
        safe_items = []
        for key, value in session_context.items():
            if len(safe_items) >= 8:
                break
            if not isinstance(key, str) or not _is_safe_primitive(value):
                continue
            safe_items.append(
                (
                    _sanitize_text(key, 64),
                    _sanitize_text(str(value), MAX_SAFE_TEXT_LENGTH),
                )
            )
        return tuple(safe_items)

    def _project_device(self, device):
        formal_capabilities = [
            capability
            for capability in device.capabilities
            if isinstance(capability, DeviceCapability)
        ][:MAX_CAPABILITIES_PER_DEVICE]
        capabilities = tuple(
            self._project_capability(capability) for capability in formal_capabilities
        )
        return AISafeDevice(
            device_id=_sanitize_text(device.id, 128),
            display_name=_sanitize_text(device.name, MAX_SAFE_TEXT_LENGTH),
            device_type=_sanitize_text(device.type, 128),
            capabilities=capabilities,
            state=self._project_state(device.state),
        )

    def _project_capability(self, capability):
        parameters = []
        for name, descriptor in capability.parameters.items():
            if not isinstance(name, str) or not isinstance(descriptor, dict):
                continue
            safe_descriptor = {
                "name": _sanitize_text(name, 64),
                "type": _sanitize_text(str(descriptor.get("type", "string")), 64),
                "required": bool(descriptor.get("required", False)),
            }
            parameters.append(tuple(sorted(safe_descriptor.items())))
        return AISafeCapability(
            name=_sanitize_text(capability.name, 128),
            kind=capability.kind,
            parameters=tuple(parameters),
        )

    def _project_state(self, state):
        properties = []
        for key, value in state.properties.items():
            if len(properties) >= MAX_PROPERTIES_PER_DEVICE:
                break
            if not _is_safe_property(key, value):
                continue
            properties.append((_sanitize_text(key, 64), _sanitize_property_value(value)))
        return AISafeDeviceState(
            status=_sanitize_text(state.status, 64),
            semantic_properties=tuple(properties),
            updated_at=state.updated_at,
        )


def command_grammar_catalog():
    """Return a small structured grammar projection for current AI tests."""
    return (
        (
            ("command", "device read"),
            ("operation", "read"),
            ("required", "device_id capability"),
            ("example", "device read lamp_1 status.read"),
            ("classification", "read"),
        ),
        (
            ("command", "device apply"),
            ("operation", "apply"),
            ("required", "device_id capability parameters"),
            ("example", "device apply lamp_1 power.switch state=true"),
            ("classification", "mutate"),
        ),
        (
            ("command", "device state"),
            ("operation", "state"),
            ("required", "device_id"),
            ("example", "device state lamp_1"),
            ("classification", "read"),
        ),
        (
            ("command", "device list"),
            ("operation", "list"),
            ("required", ""),
            ("example", "device list"),
            ("classification", "read"),
        ),
    )


def _is_safe_property(key, value):
    if not isinstance(key, str) or not SAFE_PROPERTY_NAME.match(key):
        return False
    if key.lower() in TECHNICAL_PROPERTY_NAMES:
        return False
    return _is_safe_primitive(value)


def _is_safe_primitive(value):
    return value is None or isinstance(value, (bool, int, float, str))


def _sanitize_property_value(value):
    if isinstance(value, str):
        return _sanitize_text(value, MAX_SAFE_TEXT_LENGTH)
    return value


def _sanitize_text(value, max_length):
    if not isinstance(value, str):
        value = str(value)
    sanitized = "".join(ch for ch in value if ch >= " " and ch != "\x7f")
    sanitized = sanitized.strip()
    if not sanitized:
        return "unknown"
    return sanitized[:max_length]
