import unittest

from jarvis_core.capabilities.catalog import (
    DEVICE_CATALOG_COMMAND,
    DEVICE_NOT_FOUND,
    DEVICE_REGISTRY_UNAVAILABLE,
    INVALID_DEVICE_CATALOG_COMMAND,
    UNSUPPORTED_DEVICE_CATALOG_OPERATION,
    DeviceCatalogCapability,
)
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.domain import CapabilityResult, Command, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.registry import CapabilityRegistry


class DeviceCatalogCapabilityTest(unittest.TestCase):
    def build_context(self, registry=None):
        return RuntimeContext(
            event_bus=EventBus(),
            capability_registry=CapabilityRegistry(),
            device_registry=registry if registry is not None else DeviceRegistry(),
        )

    def build_device(self):
        return Device(
            id="sensor_1",
            name="Temperature Sensor",
            type="sensor",
            capabilities=[
                DeviceCapability(
                    name="temperature.read",
                    kind="reading",
                    parameters={"unit": {"required": False}},
                    constraints={"min": -40},
                    availability_policy={"mode": "always"},
                    metadata={"internal": "not exposed"},
                ),
                "legacy.temperature",
            ],
            state=DeviceState(
                status="known",
                properties={"temperature": 22},
                updated_at="2026-07-12T19:00:00+00:00",
            ),
            metadata={"secret": "do not expose"},
        )

    def test_list_empty_catalog(self):
        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "list"},
            ),
            self.build_context(),
        )

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertEqual(result.message, "No devices registered.")
        self.assertEqual(result.data, {"count": 0, "devices": []})

    def test_list_devices_returns_safe_summaries(self):
        registry = DeviceRegistry()
        registry.register(self.build_device())

        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "list"},
            ),
            self.build_context(registry),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(
            result.data["devices"][0],
            {
                "id": "sensor_1",
                "name": "Temperature Sensor",
                "type": "sensor",
                "status": "known",
                "formal_capability_count": 1,
                "legacy_capability_count": 1,
            },
        )
        self.assertNotIn("secret", str(result.data))

    def test_info_returns_safe_device_details(self):
        registry = DeviceRegistry()
        registry.register(self.build_device())

        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "info", "device_id": "sensor_1"},
            ),
            self.build_context(registry),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data["device"]["id"], "sensor_1")
        self.assertEqual(result.data["device"]["status"], "known")
        self.assertNotIn("metadata", result.data["device"])
        self.assertNotIn("secret", str(result.data))

    def test_capabilities_separates_formal_and_legacy(self):
        registry = DeviceRegistry()
        registry.register(self.build_device())

        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "capabilities", "device_id": "sensor_1"},
            ),
            self.build_context(registry),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data["device_id"], "sensor_1")
        self.assertEqual(result.data["legacy"], ["legacy.temperature"])
        self.assertEqual(result.data["formal"][0]["name"], "temperature.read")
        self.assertEqual(result.data["formal"][0]["kind"], "reading")
        self.assertNotIn("metadata", result.data["formal"][0])
        self.assertNotIn("internal", str(result.data))

    def test_state_returns_official_device_state(self):
        registry = DeviceRegistry()
        registry.register(self.build_device())

        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "state", "device_id": "sensor_1"},
            ),
            self.build_context(registry),
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.data,
            {
                "device_id": "sensor_1",
                "state": {
                    "status": "known",
                    "properties": {"temperature": 22},
                    "updated_at": "2026-07-12T19:00:00+00:00",
                },
            },
        )

    def test_missing_device_returns_safe_failure(self):
        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "info", "device_id": "missing"},
            ),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, DEVICE_NOT_FOUND)
        self.assertEqual(result.message, "Device not found.")
        self.assertEqual(
            result.data,
            {"operation": "info", "device_id": "missing"},
        )

    def test_invalid_command_name_returns_safe_failure(self):
        result = DeviceCatalogCapability().run(
            Command(name="wrong.command", args={"operation": "list"}),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, INVALID_DEVICE_CATALOG_COMMAND)

    def test_unsupported_operation_returns_safe_failure(self):
        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "delete", "device_id": "sensor_1"},
            ),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, UNSUPPORTED_DEVICE_CATALOG_OPERATION)

    def test_missing_device_id_returns_safe_failure(self):
        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "info"},
            ),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, INVALID_DEVICE_CATALOG_COMMAND)
        self.assertEqual(result.data, {"operation": "info"})

    def test_missing_device_registry_returns_safe_failure(self):
        context = RuntimeContext(
            event_bus=EventBus(),
            capability_registry=CapabilityRegistry(),
        )

        result = DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "list"},
            ),
            context,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, DEVICE_REGISTRY_UNAVAILABLE)

    def test_catalog_queries_do_not_mutate_registry(self):
        registry = DeviceRegistry()
        device = self.build_device()
        registry.register(device)

        DeviceCatalogCapability().run(
            Command(
                name=DEVICE_CATALOG_COMMAND,
                args={"operation": "state", "device_id": "sensor_1"},
            ),
            self.build_context(registry),
        )

        self.assertIs(registry.get("sensor_1"), device)
        self.assertEqual(registry.get("sensor_1").state.properties, {"temperature": 22})


if __name__ == "__main__":
    unittest.main()
