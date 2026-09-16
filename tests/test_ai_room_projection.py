import unittest

from jarvis_core.ai.context import SafeContextBuilder
from jarvis_core.ai.contracts import AISafeDevice, AISafeDeviceState
from jarvis_core.devices import Device, DeviceRegistry, DeviceState, room_label


class SafeContextRoomProjectionTests(unittest.TestCase):
    def setUp(self):
        self.builder = SafeContextBuilder()

    def project_device(self, metadata):
        registry = DeviceRegistry()
        registry.register(
            Device(
                id="lamp_1",
                name="Lámpara",
                type="light",
                state=DeviceState(status="known", properties={"power": False}),
                metadata=metadata,
            )
        )
        context = self.builder.build("lee el estado", registry)
        return context.devices[0]

    def test_metadata_room_projects_into_safe_device(self):
        device = self.project_device({"room": "Cuarto"})

        self.assertEqual(device.room, "Cuarto")

    def test_room_preserves_original_accents_and_case(self):
        device = self.project_device({"room": "Habitación Principal"})

        self.assertEqual(device.room, "Habitación Principal")

    def test_blank_room_projects_to_none(self):
        device = self.project_device({"room": "   "})

        self.assertIsNone(device.room)

    def test_unsupported_room_value_projects_to_none(self):
        device = self.project_device({"room": 17})

        self.assertIsNone(device.room)

    def test_oversized_room_projects_to_none(self):
        device = self.project_device({"room": "x" * 65})

        self.assertIsNone(device.room)

    def test_path_like_room_projects_to_none(self):
        for value in ("cuarto/test", "cuarto\\test"):
            with self.subTest(value=value):
                self.assertIsNone(self.project_device({"room": value}).room)

    def test_url_like_room_projects_to_none(self):
        device = self.project_device({"room": "https://example.invalid"})

        self.assertIsNone(device.room)

    def test_ip_like_room_projects_to_none(self):
        device = self.project_device({"room": "192.168.1.50"})

        self.assertIsNone(device.room)

    def test_technical_room_value_projects_to_none(self):
        device = self.project_device({"room": "localhost:8080"})

        self.assertIsNone(device.room)

    def test_room_without_configured_room_projects_to_none(self):
        device = self.project_device({})

        self.assertIsNone(device.room)

    def test_room_annotation_is_optional_union(self):
        self.assertEqual(AISafeDevice.__annotations__["room"], str | None)
        default = AISafeDevice(
            device_id="a",
            display_name="b",
            device_type="c",
            state=AISafeDeviceState("known"),
        )
        self.assertIsNone(default.room)

    def test_raw_metadata_blob_is_never_exposed(self):
        device = self.project_device({"room": "sala", "serial": "abc", "url": "http://x"})

        self.assertEqual(device.room, "sala")
        self.assertFalse(hasattr(device, "metadata"))
        self.assertFalse(hasattr(device, "serial"))


class RoomLabelValidationTests(unittest.TestCase):
    def test_allowed_label_preserved(self):
        self.assertEqual(room_label("Estudio.2-Garage_u3"), "Estudio.2-Garage_u3")

    def test_accented_letter_allowed(self):
        self.assertEqual(room_label("Recámara"), "Recámara")

    def test_rejects_disallowed_symbols(self):
        for value in ("sala@", "sala#1", "sala:principal", "sala+1", "sala=1", "sala%", "sala&"):
            with self.subTest(value=value):
                self.assertIsNone(room_label(value))

    def test_rejects_blank_and_non_string(self):
        self.assertIsNone(room_label(""))
        self.assertIsNone(room_label(None))
        self.assertIsNone(room_label(17))


if __name__ == "__main__":
    unittest.main()