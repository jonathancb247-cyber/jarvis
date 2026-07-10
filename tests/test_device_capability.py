import unittest

from jarvis_core.devices import Device, DeviceCapability


class DeviceCapabilityTest(unittest.TestCase):
    def test_valid_action_capability(self):
        capability = DeviceCapability(
            name="power.switch",
            kind="action",
            parameters={
                "state": {
                    "type": "string",
                    "required": True,
                    "constraints": {"enum": ["on", "off"]},
                    "metadata": {"unit": "state"},
                }
            },
        )

        self.assertEqual(capability.name, "power.switch")
        self.assertEqual(capability.kind, "action")

    def test_valid_reading_capability(self):
        capability = DeviceCapability(name="temperature.read", kind="reading")

        self.assertEqual(capability.name, "temperature.read")
        self.assertEqual(capability.kind, "reading")

    def test_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            DeviceCapability(name="", kind="action")

    def test_rejects_invalid_kind(self):
        with self.assertRaises(ValueError):
            DeviceCapability(name="power.switch", kind="driver")

    def test_rejects_invalid_parameters(self):
        with self.assertRaises(ValueError):
            DeviceCapability(name="power.switch", kind="action", parameters=[])

    def test_rejects_empty_parameter_name(self):
        with self.assertRaises(ValueError):
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"": {"type": "string"}},
            )

    def test_rejects_non_dict_parameter_descriptor(self):
        with self.assertRaises(ValueError):
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": "on"},
            )

    def test_rejects_non_bool_required(self):
        with self.assertRaises(ValueError):
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"required": "yes"}},
            )

    def test_rejects_invalid_parameter_constraints(self):
        with self.assertRaises(ValueError):
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"constraints": []}},
            )

    def test_rejects_invalid_parameter_metadata(self):
        with self.assertRaises(ValueError):
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"metadata": []}},
            )

    def test_rejects_invalid_capability_constraints(self):
        with self.assertRaises(ValueError):
            DeviceCapability(name="power.switch", kind="action", constraints=[])

    def test_rejects_invalid_availability_policy(self):
        with self.assertRaises(ValueError):
            DeviceCapability(
                name="power.switch",
                kind="action",
                availability_policy=[],
            )

    def test_rejects_invalid_metadata(self):
        with self.assertRaises(ValueError):
            DeviceCapability(name="power.switch", kind="action", metadata=[])

    def test_device_accepts_device_capability(self):
        capability = DeviceCapability(name="power.switch", kind="action")

        device = Device(
            id="light_1",
            name="Light 1",
            type="light",
            capabilities=[capability],
        )

        self.assertEqual(device.capabilities, [capability])

    def test_device_preserves_legacy_string_descriptors(self):
        device = Device(
            id="light_1",
            name="Light 1",
            type="light",
            capabilities=["turn_on", "turn_off"],
        )

        self.assertEqual(device.capabilities, ["turn_on", "turn_off"])

    def test_device_rejects_invalid_capability_values(self):
        with self.assertRaises(ValueError):
            Device(
                id="light_1",
                name="Light 1",
                type="light",
                capabilities=[object()],
            )

    def test_device_rejects_empty_legacy_string_descriptor(self):
        with self.assertRaises(ValueError):
            Device(
                id="light_1",
                name="Light 1",
                type="light",
                capabilities=[""],
            )


if __name__ == "__main__":
    unittest.main()
