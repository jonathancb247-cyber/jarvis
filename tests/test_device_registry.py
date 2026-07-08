import unittest

from jarvis_core.devices import Device, DeviceRegistry, DeviceState


class DeviceRegistryTest(unittest.TestCase):
    def test_register_and_get_device(self):
        registry = DeviceRegistry()
        device = Device(
            id="living_room_light",
            name="Living Room Light",
            type="light",
            capabilities=["turn_on", "turn_off"],
        )

        registry.register(device)

        self.assertIs(registry.get("living_room_light"), device)

    def test_register_duplicate_device_raises_value_error(self):
        registry = DeviceRegistry()
        device = Device(id="device_1", name="Device 1", type="sensor")
        registry.register(device)

        with self.assertRaises(ValueError):
            registry.register(device)

    def test_get_missing_device_raises_key_error(self):
        registry = DeviceRegistry()

        with self.assertRaises(KeyError):
            registry.get("missing")

    def test_list_returns_registered_devices(self):
        registry = DeviceRegistry()
        light = Device(id="light_1", name="Light 1", type="light")
        sensor = Device(id="sensor_1", name="Sensor 1", type="sensor")
        registry.register(light)
        registry.register(sensor)

        self.assertEqual(registry.list(), [light, sensor])

    def test_find_by_name_returns_matching_devices(self):
        registry = DeviceRegistry()
        light = Device(id="light_1", name="Kitchen Light", type="light")
        sensor = Device(id="sensor_1", name="Kitchen Sensor", type="sensor")
        registry.register(light)
        registry.register(sensor)

        self.assertEqual(registry.find_by_name("Kitchen Light"), [light])

    def test_find_by_type_returns_matching_devices(self):
        registry = DeviceRegistry()
        kitchen = Device(id="kitchen_light", name="Kitchen Light", type="light")
        bedroom = Device(id="bedroom_light", name="Bedroom Light", type="light")
        sensor = Device(id="sensor_1", name="Sensor 1", type="sensor")
        registry.register(kitchen)
        registry.register(bedroom)
        registry.register(sensor)

        self.assertEqual(registry.find_by_type("light"), [kitchen, bedroom])

    def test_update_state_replaces_known_device_state(self):
        registry = DeviceRegistry()
        device = Device(id="fan_1", name="Fan 1", type="fan")
        state = DeviceState(
            status="on",
            properties={"speed": "low"},
            updated_at="2026-07-08T13:00:00Z",
        )
        registry.register(device)

        updated = registry.update_state("fan_1", state)

        self.assertIs(updated, device)
        self.assertEqual(registry.get("fan_1").state, state)

    def test_update_state_for_missing_device_raises_key_error(self):
        registry = DeviceRegistry()

        with self.assertRaises(KeyError):
            registry.update_state("missing", DeviceState(status="off"))

    def test_has_reports_registered_device(self):
        registry = DeviceRegistry()
        registry.register(Device(id="door_1", name="Door 1", type="door"))

        self.assertTrue(registry.has("door_1"))
        self.assertFalse(registry.has("missing"))


if __name__ == "__main__":
    unittest.main()
