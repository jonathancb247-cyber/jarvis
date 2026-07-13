import unittest

from jarvis_core.bootstrap import (
    build_http_runtime,
    build_runtime,
    build_runtime_from_profile,
)
from jarvis_core.configuration import RuntimeConfigurationLoader
from jarvis_core.devices import Device, DeviceCapability
from jarvis_core.http_driver import (
    HttpDeviceBinding,
    HttpDeviceBindingStore,
    HttpDeviceDriver,
    HttpJsonResponse,
)


class FakeHttpTransport:
    def __init__(self):
        self.calls = []

    def post_json(self, url, payload, timeout_seconds, max_response_bytes):
        self.calls.append((url, payload, timeout_seconds, max_response_bytes))
        return HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": True}},
        )


class BootstrapTests(unittest.TestCase):
    def make_http_runtime(self):
        store = HttpDeviceBindingStore()
        store.register(HttpDeviceBinding("lamp_1", "http://localhost:8000"))
        transport = FakeHttpTransport()
        driver = HttpDeviceDriver(store, transport=transport)
        device = Device(
            id="lamp_1",
            name="Lamp",
            type="light",
            capabilities=[
                DeviceCapability(
                    name="power.switch",
                    kind="action",
                    parameters={"state": {"type": "string", "required": True}},
                ),
                DeviceCapability(name="status.read", kind="reading"),
            ],
        )
        return build_http_runtime(driver, devices=[device]), transport

    def test_default_runtime_has_no_demo_device_and_uses_no_http_network(self):
        runtime = build_runtime()

        result = runtime.handle_adapter_input("device list")

        self.assertTrue(result.success)
        self.assertEqual({"count": 0, "devices": []}, result.data)

    def test_default_runtime_still_handles_time(self):
        runtime = build_runtime()

        result = runtime.handle_adapter_input("what time is it?")

        self.assertTrue(result.success)
        self.assertTrue(result.message.startswith("The current time is "))

    def test_http_runtime_vertical_slice_uses_fake_transport(self):
        runtime, transport = self.make_http_runtime()

        apply_result = runtime.handle_adapter_input(
            "device apply lamp_1 power.switch state=true",
            source="cli",
        )
        read_result = runtime.handle_adapter_input(
            "device read lamp_1 status.read",
            source="cli",
        )
        state_result = runtime.handle_adapter_input("device state lamp_1", source="cli")

        self.assertTrue(apply_result.success)
        self.assertEqual("Device action completed.", apply_result.message)
        self.assertTrue(read_result.success)
        self.assertTrue(state_result.success)
        self.assertEqual({"power": True}, state_result.data["state"]["properties"])
        self.assertEqual(2, len(transport.calls))

    def test_build_http_runtime_rejects_invalid_driver(self):
        with self.assertRaises(TypeError):
            build_http_runtime(object())

    def test_build_runtime_from_profile_uses_fake_http_transport(self):
        profile = RuntimeConfigurationLoader().load("profiles/http-lab.example.json")
        transport = FakeHttpTransport()
        runtime = build_runtime_from_profile(profile, http_transport=transport)

        apply_result = runtime.handle_adapter_input(
            "device apply lamp_1 power.switch state=true",
            source="cli",
        )
        read_result = runtime.handle_adapter_input(
            "device read lamp_1 status.read",
            source="cli",
        )
        state_result = runtime.handle_adapter_input("device state lamp_1", source="cli")
        list_result = runtime.handle_adapter_input("device list", source="cli")

        self.assertTrue(apply_result.success)
        self.assertTrue(read_result.success)
        self.assertTrue(state_result.success)
        self.assertEqual(state_result.data["state"]["properties"], {"power": True})
        self.assertEqual(list_result.data["count"], 1)
        self.assertEqual(transport.calls[0][0], "http://192.168.1.50/device/apply")
        self.assertEqual(transport.calls[1][0], "http://192.168.1.50/device/read")


if __name__ == "__main__":
    unittest.main()
