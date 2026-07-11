import unittest

from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.drivers import (
    DRIVER_UNAVAILABLE,
    DriverResult,
    SimulatedDriver,
)


class TrackingDeviceRegistry(DeviceRegistry):
    def __init__(self):
        super().__init__()
        self.update_calls = []

    def update_state(self, device_id, state):
        self.update_calls.append((device_id, state))
        return super().update_state(device_id, state)


class DeviceStateCoordinatorTests(unittest.TestCase):
    def make_device(self):
        return Device(
            id="device-1",
            name="Desk Lamp",
            type="light",
            capabilities=[
                DeviceCapability(name="temperature.read", kind="reading"),
                DeviceCapability(name="power.set", kind="action"),
            ],
            state=DeviceState(status="unknown", properties={"enabled": False}),
        )

    def make_registry(self, device):
        registry = TrackingDeviceRegistry()
        registry.register(device)
        return registry

    def test_successful_read_updates_properties_and_status_known(self):
        device = self.make_device()
        registry = self.make_registry(device)
        driver = SimulatedDriver()
        driver.set_reading(
            device.id,
            "temperature.read",
            {"value": 22.5, "unit": "celsius"},
        )
        result = driver.read(device, "temperature.read")

        state = DeviceStateCoordinator().coordinate(
            device,
            "temperature.read",
            "read",
            result,
            registry,
        )

        self.assertEqual("known", state.status)
        self.assertEqual(
            {"enabled": False, "value": 22.5, "unit": "celsius"},
            state.properties,
        )
        self.assertIsNotNone(state.updated_at)
        self.assertIs(registry.get(device.id).state, state)
        self.assertEqual(1, len(registry.update_calls))

    def test_action_with_approved_observations_updates_state(self):
        device = self.make_device()
        registry = self.make_registry(device)
        result = DriverResult(True, {"enabled": True}, None)

        state = DeviceStateCoordinator().coordinate(
            device,
            "power.set",
            "apply",
            result,
            registry,
        )

        self.assertEqual("known", state.status)
        self.assertEqual({"enabled": True}, state.properties)
        self.assertEqual(1, len(registry.update_calls))

    def test_action_without_approved_observations_preserves_current_state(self):
        device = self.make_device()
        registry = self.make_registry(device)
        driver = SimulatedDriver()
        result = driver.apply(device, "power.set", {"enabled": True})
        original_state = device.state

        state = DeviceStateCoordinator().coordinate(
            device,
            "power.set",
            "apply",
            result,
            registry,
        )

        self.assertIs(original_state, state)
        self.assertEqual({"enabled": False}, device.state.properties)
        self.assertEqual(0, len(registry.update_calls))

    def test_missing_capability_does_not_update_state(self):
        device = self.make_device()
        registry = self.make_registry(device)
        original_state = device.state
        result = DriverResult(True, {"value": 40}, None)

        state = DeviceStateCoordinator().coordinate(
            device,
            "humidity.read",
            "read",
            result,
            registry,
        )

        self.assertIs(original_state, state)
        self.assertEqual(0, len(registry.update_calls))

    def test_invalid_driver_result_is_contract_error(self):
        device = self.make_device()
        registry = self.make_registry(device)

        with self.assertRaises(TypeError):
            DeviceStateCoordinator().coordinate(
                device,
                "temperature.read",
                "read",
                object(),
                registry,
            )

    def test_unavailable_updates_status_without_copying_error(self):
        device = self.make_device()
        registry = self.make_registry(device)
        result = DriverResult(False, {}, DRIVER_UNAVAILABLE)

        state = DeviceStateCoordinator().coordinate(
            device,
            "temperature.read",
            "read",
            result,
            registry,
        )

        self.assertEqual("unavailable", state.status)
        self.assertEqual({"enabled": False}, state.properties)
        self.assertIsNotNone(state.updated_at)
        self.assertEqual(1, len(registry.update_calls))

    def test_driver_does_not_modify_device_state(self):
        device = self.make_device()
        registry = self.make_registry(device)
        driver = SimulatedDriver()
        original_state = device.state

        driver.set_reading(device.id, "temperature.read", {"value": 20})
        result = driver.read(device, "temperature.read")

        self.assertIs(original_state, device.state)

        DeviceStateCoordinator().coordinate(
            device,
            "temperature.read",
            "read",
            result,
            registry,
        )

        self.assertIsNot(original_state, device.state)
        self.assertEqual({"enabled": False, "value": 20}, device.state.properties)

    def test_device_registry_changes_only_through_coordinator(self):
        device = self.make_device()
        registry = self.make_registry(device)
        driver = SimulatedDriver()
        driver.set_reading(device.id, "temperature.read", {"value": 21})

        result = driver.read(device, "temperature.read")

        self.assertEqual(0, len(registry.update_calls))
        self.assertEqual({"enabled": False}, device.state.properties)

        DeviceStateCoordinator().coordinate(
            device,
            "temperature.read",
            "read",
            result,
            registry,
        )

        self.assertEqual(1, len(registry.update_calls))
        self.assertEqual({"enabled": False, "value": 21}, device.state.properties)

    def test_technical_metadata_errors_and_parameters_are_not_copied(self):
        device = self.make_device()
        registry = self.make_registry(device)
        result = DriverResult(
            True,
            {
                "enabled": True,
                "metadata": {"internal": True},
                "error": "ignored",
                "parameters": {"enabled": True},
            },
            None,
        )

        state = DeviceStateCoordinator().coordinate(
            device,
            "power.set",
            "apply",
            result,
            registry,
        )

        self.assertEqual({"enabled": True}, state.properties)

    def test_invalid_operation_is_contract_error(self):
        device = self.make_device()
        registry = self.make_registry(device)

        with self.assertRaises(ValueError):
            DeviceStateCoordinator().coordinate(
                device,
                "temperature.read",
                "poll",
                DriverResult(True, {"value": 1}, None),
                registry,
            )


if __name__ == "__main__":
    unittest.main()
