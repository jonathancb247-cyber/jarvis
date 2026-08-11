import unittest

from jarvis_core.devices import Device
from jarvis_core.driver_selection import DeviceTransportDriver
from jarvis_core.drivers import DRIVER_UNAVAILABLE, DriverResult


class FakeDriver:
    def __init__(self, label):
        self.label = label
        self.calls = []
        self.closed = False

    def read(self, device, capability_name):
        self.calls.append(("read", device.id, capability_name))
        return DriverResult(True, {"driver": self.label}, None)

    def apply(self, device, capability_name, parameters):
        self.calls.append(("apply", device.id, capability_name, parameters.copy()))
        return DriverResult(True, {"driver": self.label}, None)

    def close(self):
        self.closed = True


class DeviceTransportDriverTests(unittest.TestCase):
    def test_delegates_by_device_id_without_runtime_branching(self):
        selector = DeviceTransportDriver()
        http_driver = FakeDriver("http")
        mqtt_driver = FakeDriver("mqtt")
        selector.register("lamp_1", http_driver)
        selector.register("temperature_room", mqtt_driver)

        http_result = selector.read(Device("lamp_1", "Lamp", "light"), "status.read")
        mqtt_result = selector.read(
            Device("temperature_room", "Room", "sensor"),
            "temperature.read",
        )

        self.assertEqual({"driver": "http"}, http_result.observations)
        self.assertEqual({"driver": "mqtt"}, mqtt_result.observations)
        self.assertEqual([("read", "lamp_1", "status.read")], http_driver.calls)
        self.assertEqual(
            [("read", "temperature_room", "temperature.read")],
            mqtt_driver.calls,
        )

    def test_missing_driver_returns_driver_unavailable(self):
        selector = DeviceTransportDriver()

        result = selector.read(Device("missing", "Missing", "sensor"), "status.read")

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_UNAVAILABLE, result.error)

    def test_rejects_duplicate_device_driver(self):
        selector = DeviceTransportDriver()
        selector.register("lamp_1", FakeDriver("http"))

        with self.assertRaises(ValueError):
            selector.register("lamp_1", FakeDriver("mqtt"))

    def test_close_closes_each_unique_driver_once(self):
        selector = DeviceTransportDriver()
        driver = FakeDriver("shared")
        selector.register("lamp_1", driver)
        selector.register("lamp_2", driver)

        selector.close()

        self.assertTrue(driver.closed)


if __name__ == "__main__":
    unittest.main()
