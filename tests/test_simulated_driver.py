import unittest

from jarvis_core.devices import Device, DeviceCapability, DeviceState
from jarvis_core.drivers import (
    CAPABILITY_NOT_FOUND,
    DRIVER_UNAVAILABLE,
    INVALID_CAPABILITY_KIND,
    INVALID_DEVICE,
    INVALID_PARAMETERS,
    SIMULATED_FAILURE,
    SIMULATED_TIMEOUT,
    DriverResult,
    SimulatedDriver,
)


class DriverResultTests(unittest.TestCase):
    def test_driver_result_valid(self):
        result = DriverResult(True, {"value": 1}, None)

        self.assertTrue(result.success)
        self.assertEqual({"value": 1}, result.observations)
        self.assertIsNone(result.error)

    def test_driver_result_invalid(self):
        invalid_results = [
            {"success": "yes", "observations": {}, "error": None},
            {"success": True, "observations": [], "error": None},
            {"success": False, "observations": {}, "error": ""},
            {"success": False, "observations": {}, "error": 123},
        ]

        for kwargs in invalid_results:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    DriverResult(**kwargs)


class SimulatedDriverTests(unittest.TestCase):
    def make_device(self):
        return Device(
            id="device-1",
            name="Desk Lamp",
            type="light",
            capabilities=[
                DeviceCapability(name="temperature.read", kind="reading"),
                DeviceCapability(
                    name="power.set",
                    kind="action",
                    parameters={
                        "enabled": {
                            "type": "bool",
                            "required": True,
                            "constraints": {},
                            "metadata": {},
                        }
                    },
                ),
            ],
            state=DeviceState(status="online", properties={"enabled": False}),
        )

    def test_is_available(self):
        device = self.make_device()
        driver = SimulatedDriver()

        self.assertTrue(driver.is_available(device))

        driver.set_available(False)

        self.assertFalse(driver.is_available(device))
        self.assertFalse(driver.is_available(object()))

    def test_valid_read(self):
        device = self.make_device()
        driver = SimulatedDriver()
        driver.set_reading(
            "device-1",
            "temperature.read",
            {"value": 22.5, "unit": "celsius"},
        )

        result = driver.read(device, "temperature.read")

        self.assertTrue(result.success)
        self.assertEqual(
            {"value": 22.5, "unit": "celsius"},
            result.observations,
        )
        self.assertIsNone(result.error)

    def test_valid_action(self):
        device = self.make_device()
        driver = SimulatedDriver()

        result = driver.apply(device, "power.set", {"enabled": True})

        self.assertTrue(result.success)
        self.assertEqual(
            {
                "applied": True,
                "capability": "power.set",
                "parameters": {"enabled": True},
            },
            result.observations,
        )
        self.assertIsNone(result.error)

    def test_missing_capability(self):
        device = self.make_device()
        driver = SimulatedDriver()

        result = driver.read(device, "humidity.read")

        self.assertFalse(result.success)
        self.assertEqual({}, result.observations)
        self.assertEqual(CAPABILITY_NOT_FOUND, result.error)

    def test_invalid_device_returns_structured_error(self):
        driver = SimulatedDriver()

        result = driver.read(object(), "temperature.read")

        self.assertFalse(result.success)
        self.assertEqual({}, result.observations)
        self.assertEqual(INVALID_DEVICE, result.error)

    def test_driver_unavailable_returns_structured_error(self):
        device = self.make_device()
        driver = SimulatedDriver(available=False)

        result = driver.read(device, "temperature.read")

        self.assertFalse(result.success)
        self.assertEqual({}, result.observations)
        self.assertEqual(DRIVER_UNAVAILABLE, result.error)

    def test_read_rejects_action_capability(self):
        device = self.make_device()
        driver = SimulatedDriver()

        result = driver.read(device, "power.set")

        self.assertFalse(result.success)
        self.assertEqual(INVALID_CAPABILITY_KIND, result.error)

    def test_apply_rejects_reading_capability(self):
        device = self.make_device()
        driver = SimulatedDriver()

        result = driver.apply(device, "temperature.read", {})

        self.assertFalse(result.success)
        self.assertEqual(INVALID_CAPABILITY_KIND, result.error)

    def test_apply_rejects_invalid_parameters(self):
        device = self.make_device()
        driver = SimulatedDriver()

        result = driver.apply(device, "power.set", None)

        self.assertFalse(result.success)
        self.assertEqual({}, result.observations)
        self.assertEqual(INVALID_PARAMETERS, result.error)

    def test_simulated_failure(self):
        device = self.make_device()
        driver = SimulatedDriver()
        driver.simulate_failure("apply", "power.set")

        result = driver.apply(device, "power.set", {"enabled": True})

        self.assertFalse(result.success)
        self.assertEqual({}, result.observations)
        self.assertEqual(SIMULATED_FAILURE, result.error)

    def test_simulated_timeout_is_immediate_error(self):
        device = self.make_device()
        driver = SimulatedDriver()
        driver.simulate_timeout("read", "temperature.read")

        result = driver.read(device, "temperature.read")

        self.assertFalse(result.success)
        self.assertEqual({}, result.observations)
        self.assertEqual(SIMULATED_TIMEOUT, result.error)

    def test_simulated_driver_does_not_modify_device_state(self):
        device = self.make_device()
        original_state = device.state
        driver = SimulatedDriver()

        driver.read(device, "temperature.read")
        driver.apply(device, "power.set", {"enabled": True})

        self.assertIs(original_state, device.state)
        self.assertEqual("online", device.state.status)
        self.assertEqual({"enabled": False}, device.state.properties)

    def test_simulated_driver_does_not_require_runtime(self):
        driver = SimulatedDriver()

        self.assertFalse(hasattr(driver, "runtime"))

    def test_simulated_driver_does_not_require_device_registry(self):
        driver = SimulatedDriver()

        self.assertFalse(hasattr(driver, "device_registry"))

    def test_simulated_driver_does_not_publish_events(self):
        driver = SimulatedDriver()

        self.assertFalse(hasattr(driver, "event_bus"))


if __name__ == "__main__":
    unittest.main()
