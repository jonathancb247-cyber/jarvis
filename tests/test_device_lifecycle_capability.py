import unittest

from jarvis_core.capabilities.lifecycle import (
    DEVICE_ALREADY_EXISTS,
    DEVICE_LIFECYCLE_COMMAND,
    DEVICE_NOT_FOUND,
    DEVICE_REGISTRY_UNAVAILABLE,
    INVALID_DEVICE_LIFECYCLE_COMMAND,
    DeviceLifecycleCapability,
    DeviceLifecycleRegistrar,
)
from jarvis_core.devices import Device, DeviceRegistry
from jarvis_core.domain import CapabilityResult, Command, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.registry import CapabilityRegistry


class DeviceLifecycleCapabilityTest(unittest.TestCase):
    def build_context(self, registry=None):
        return RuntimeContext(
            event_bus=EventBus(),
            capability_registry=CapabilityRegistry(),
            device_registry=registry if registry is not None else DeviceRegistry(),
        )

    def lifecycle_command(self, args):
        return Command(name=DEVICE_LIFECYCLE_COMMAND, args=args, source="cli")

    def test_add_success(self):
        registry = DeviceRegistry()

        result = DeviceLifecycleCapability().run(
            self.lifecycle_command(
                {
                    "operation": "add",
                    "device_id": "lamp_1",
                    "name": "Lamp",
                    "type": "light",
                }
            ),
            self.build_context(registry),
        )

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertEqual(result.message, "Device registered.")
        self.assertEqual(result.error, None)
        self.assertEqual(result.data, {"operation": "add", "device_id": "lamp_1"})
        device = registry.get("lamp_1")
        self.assertEqual(device.id, "lamp_1")
        self.assertEqual(device.name, "Lamp")
        self.assertEqual(device.type, "light")
        self.assertEqual(device.capabilities, [])
        self.assertEqual(device.state.status, "unknown")
        self.assertEqual(device.metadata, {})

    def test_remove_success(self):
        registry = DeviceRegistry()
        registry.register(Device(id="lamp_1", name="Lamp", type="light"))

        result = DeviceLifecycleCapability().run(
            self.lifecycle_command({"operation": "remove", "device_id": "lamp_1"}),
            self.build_context(registry),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message, "Device removed.")
        self.assertEqual(result.error, None)
        self.assertEqual(result.data, {"operation": "remove", "device_id": "lamp_1"})
        self.assertFalse(registry.has("lamp_1"))

    def test_add_duplicate_id_returns_safe_failure(self):
        registry = DeviceRegistry()
        registry.register(Device(id="lamp_1", name="Lamp", type="light"))

        result = DeviceLifecycleCapability().run(
            self.lifecycle_command(
                {
                    "operation": "add",
                    "device_id": "lamp_1",
                    "name": "Other",
                    "type": "light",
                }
            ),
            self.build_context(registry),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Device already exists.")
        self.assertEqual(result.error, DEVICE_ALREADY_EXISTS)
        self.assertEqual(result.data, {"operation": "add", "device_id": "lamp_1"})
        self.assertNotIn("Other", str(result.data))

    def test_remove_unknown_device_returns_safe_failure(self):
        result = DeviceLifecycleCapability().run(
            self.lifecycle_command({"operation": "remove", "device_id": "missing"}),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Device not found.")
        self.assertEqual(result.error, DEVICE_NOT_FOUND)
        self.assertEqual(result.data, {"operation": "remove", "device_id": "missing"})

    def test_registry_unavailable_returns_safe_failure(self):
        context = RuntimeContext(
            event_bus=EventBus(),
            capability_registry=CapabilityRegistry(),
        )

        result = DeviceLifecycleCapability().run(
            self.lifecycle_command({"operation": "remove", "device_id": "lamp_1"}),
            context,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Device registry is unavailable.")
        self.assertEqual(result.error, DEVICE_REGISTRY_UNAVAILABLE)
        self.assertEqual(result.data, {"operation": "remove", "device_id": "lamp_1"})

    def test_invalid_command_returns_safe_failure(self):
        result = DeviceLifecycleCapability().run(
            Command(name="wrong.command", args={"operation": "add"}),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "Device lifecycle command is invalid.")
        self.assertEqual(result.error, INVALID_DEVICE_LIFECYCLE_COMMAND)
        self.assertEqual(result.data, {})

    def test_invalid_args_return_safe_failure(self):
        result = DeviceLifecycleCapability().run(
            self.lifecycle_command(
                {
                    "operation": "add",
                    "device_id": "lamp_1",
                    "name": "",
                    "type": "light",
                }
            ),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, INVALID_DEVICE_LIFECYCLE_COMMAND)
        self.assertEqual(result.data, {"operation": "add", "device_id": "lamp_1"})

    def test_lifecycle_registrar_registers_device(self):
        registry = DeviceRegistry()
        device = Device(id="lamp_1", name="Lamp", type="light")

        result = DeviceLifecycleRegistrar().register(registry, device)

        self.assertIs(result, device)
        self.assertIs(registry.get("lamp_1"), device)

    def test_lifecycle_registrar_rejects_duplicate(self):
        registry = DeviceRegistry()
        device = Device(id="lamp_1", name="Lamp", type="light")
        registry.register(device)

        with self.assertRaises(ValueError):
            DeviceLifecycleRegistrar().register(registry, device)

    def test_lifecycle_registrar_is_not_runtime_boundary(self):
        registrar = DeviceLifecycleRegistrar()

        self.assertFalse(hasattr(registrar, "name"))
        self.assertFalse(hasattr(registrar, "run"))

    def test_lifecycle_capability_add_uses_registrar(self):
        class RecordingRegistrar:
            def __init__(self):
                self.calls = []

            def register(self, registry, device):
                self.calls.append((registry, device))
                registry.register(device)
                return device

        registrar = RecordingRegistrar()
        registry = DeviceRegistry()

        result = DeviceLifecycleCapability(registrar).run(
            self.lifecycle_command(
                {
                    "operation": "add",
                    "device_id": "lamp_1",
                    "name": "Lamp",
                    "type": "light",
                }
            ),
            self.build_context(registry),
        )

        self.assertTrue(result.success)
        self.assertEqual(len(registrar.calls), 1)
        self.assertIs(registrar.calls[0][0], registry)


if __name__ == "__main__":
    unittest.main()
