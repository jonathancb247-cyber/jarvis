import unittest

from jarvis_core.device_routing import (
    CONNECTION_FAILED_ERROR,
    DRIVER_UNAVAILABLE_ERROR,
    INVALID_RESPONSE_ERROR,
    OPERATION_NOT_SUPPORTED_ERROR,
    PROTOCOL_ERROR_ERROR,
    REQUEST_TIMEOUT_ERROR,
    DeviceCommandRouter,
)
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.domain import Command
from jarvis_core.drivers import (
    CONNECTION_FAILED,
    DRIVER_UNAVAILABLE,
    INVALID_RESPONSE,
    OPERATION_NOT_SUPPORTED,
    PROTOCOL_ERROR,
    REQUEST_TIMEOUT,
)
from jarvis_core.http_driver import (
    HttpConnectionError,
    HttpDeviceBinding,
    HttpDeviceBindingStore,
    HttpDeviceDriver,
    HttpJsonResponse,
    HttpResponseTooLargeError,
    HttpTimeoutError,
)


class FakeHttpTransport:
    def __init__(self, response=None, error=None):
        self.response = response or HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {}},
        )
        self.error = error
        self.calls = []

    def post_json(self, url, payload, timeout_seconds, max_response_bytes):
        self.calls.append(
            {
                "url": url,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        if self.error:
            raise self.error
        return self.response


class HttpDeviceDriverTests(unittest.TestCase):
    def make_device(self):
        return Device(
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
            state=DeviceState(status="unknown", properties={}),
        )

    def make_driver(self, response=None, error=None):
        store = HttpDeviceBindingStore()
        binding = HttpDeviceBinding("lamp_1", "http://localhost:8000")
        store.register(binding)
        transport = FakeHttpTransport(response=response, error=error)
        return HttpDeviceDriver(store, transport=transport), store, transport

    def test_read_success_returns_driver_result(self):
        response = HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": True}},
        )
        driver, _, transport = self.make_driver(response=response)

        result = driver.read(self.make_device(), "status.read")

        self.assertTrue(result.success)
        self.assertEqual({"power": True}, result.observations)
        self.assertIsNone(result.error)
        self.assertEqual("http://localhost:8000/device/read", transport.calls[0]["url"])
        self.assertEqual({"capability": "status.read"}, transport.calls[0]["payload"])

    def test_apply_success_returns_driver_result(self):
        response = HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": True}},
        )
        driver, _, transport = self.make_driver(response=response)

        result = driver.apply(self.make_device(), "power.switch", {"state": "true"})

        self.assertTrue(result.success)
        self.assertEqual({"power": True}, result.observations)
        self.assertEqual("http://localhost:8000/device/apply", transport.calls[0]["url"])
        self.assertEqual(
            {"capability": "power.switch", "parameters": {"state": "true"}},
            transport.calls[0]["payload"],
        )

    def test_missing_binding_is_driver_unavailable(self):
        store = HttpDeviceBindingStore()
        driver = HttpDeviceDriver(store, transport=FakeHttpTransport())

        result = driver.read(self.make_device(), "status.read")

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_UNAVAILABLE, result.error)

    def test_connection_timeout_and_oversized_response_are_normalized(self):
        cases = [
            (HttpConnectionError(), CONNECTION_FAILED),
            (HttpTimeoutError(), REQUEST_TIMEOUT),
            (HttpResponseTooLargeError(), INVALID_RESPONSE),
        ]

        for error, expected in cases:
            with self.subTest(expected=expected):
                driver, _, _ = self.make_driver(error=error)
                result = driver.read(self.make_device(), "status.read")
                self.assertFalse(result.success)
                self.assertEqual(expected, result.error)

    def test_protocol_and_invalid_response_errors(self):
        responses = [
            (
                HttpJsonResponse(
                    500,
                    "application/json",
                    {"success": False, "error": "operation_not_supported"},
                ),
                PROTOCOL_ERROR,
            ),
            (
                HttpJsonResponse(
                    200,
                    "text/plain",
                    {"success": True, "observations": {}},
                ),
                INVALID_RESPONSE,
            ),
            (
                HttpJsonResponse(200, "application/json", ["not", "dict"]),
                INVALID_RESPONSE,
            ),
            (
                HttpJsonResponse(
                    200,
                    "application/json",
                    {"success": "yes", "observations": {}},
                ),
                INVALID_RESPONSE,
            ),
        ]

        for response, expected in responses:
            with self.subTest(expected=expected):
                driver, _, _ = self.make_driver(response=response)
                result = driver.read(self.make_device(), "status.read")
                self.assertFalse(result.success)
                self.assertEqual(expected, result.error)

    def test_remote_operation_not_supported_is_normalized(self):
        response = HttpJsonResponse(
            200,
            "application/json",
            {"success": False, "error": OPERATION_NOT_SUPPORTED},
        )
        driver, _, _ = self.make_driver(response=response)

        result = driver.apply(self.make_device(), "power.switch", {"state": "true"})

        self.assertFalse(result.success)
        self.assertEqual(OPERATION_NOT_SUPPORTED, result.error)

    def test_unknown_remote_error_becomes_protocol_error(self):
        response = HttpJsonResponse(
            200,
            "application/json",
            {"success": False, "error": "stack trace: secret endpoint"},
        )
        driver, _, _ = self.make_driver(response=response)

        result = driver.read(self.make_device(), "status.read")

        self.assertFalse(result.success)
        self.assertEqual(PROTOCOL_ERROR, result.error)
        self.assertNotIn("secret endpoint", str(result.error))

    def test_no_raw_url_payload_or_exception_leaks_in_driver_result(self):
        driver, _, _ = self.make_driver(error=HttpConnectionError("http://secret.local"))

        result = driver.read(self.make_device(), "status.read")

        output = f"{result.error} {result.observations}"
        self.assertNotIn("secret.local", output)
        self.assertNotIn("status.read", output)
        self.assertNotIn("http://", output)


class HttpDeviceRouterIntegrationTests(unittest.TestCase):
    def make_router(self, response):
        registry = DeviceRegistry()
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
            state=DeviceState(status="unknown"),
        )
        registry.register(device)
        store = HttpDeviceBindingStore()
        store.register(HttpDeviceBinding("lamp_1", "http://localhost:8000"))
        driver = HttpDeviceDriver(store, transport=FakeHttpTransport(response=response))
        router = DeviceCommandRouter(registry, driver, DeviceStateCoordinator())
        return router, registry

    def command(self, operation, capability, parameters=None):
        return Command(
            name="device.execute",
            args={
                "device_id": "lamp_1",
                "capability": capability,
                "operation": operation,
                "parameters": parameters or {},
            },
            source="test",
        )

    def test_apply_route_updates_state_without_direct_router_mutation(self):
        response = HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": True}},
        )
        router, registry = self.make_router(response)

        result = router.route(
            self.command("apply", "power.switch", {"state": "true"})
        )

        self.assertTrue(result.success)
        self.assertEqual("known", result.state.status)
        self.assertEqual({"power": True}, registry.get("lamp_1").state.properties)
        self.assertEqual(
            {
                "device_id": "lamp_1",
                "capability": "power.switch",
                "operation": "apply",
            },
            result.data,
        )
        self.assertNotIn("parameters", result.data)

    def test_read_route_updates_state(self):
        response = HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": False}},
        )
        router, registry = self.make_router(response)

        result = router.route(self.command("read", "status.read"))

        self.assertTrue(result.success)
        self.assertEqual({"power": False}, registry.get("lamp_1").state.properties)

    def test_http_errors_map_to_internal_router_errors(self):
        cases = [
            (
                HttpJsonResponse(
                    200,
                    "application/json",
                    {"success": False, "error": REQUEST_TIMEOUT},
                ),
                REQUEST_TIMEOUT_ERROR,
            ),
            (
                HttpJsonResponse(
                    200,
                    "application/json",
                    {"success": False, "error": CONNECTION_FAILED},
                ),
                CONNECTION_FAILED_ERROR,
            ),
            (
                HttpJsonResponse(
                    200,
                    "application/json",
                    {"success": False, "error": INVALID_RESPONSE},
                ),
                INVALID_RESPONSE_ERROR,
            ),
            (
                HttpJsonResponse(
                    200,
                    "application/json",
                    {"success": False, "error": OPERATION_NOT_SUPPORTED},
                ),
                OPERATION_NOT_SUPPORTED_ERROR,
            ),
            (
                HttpJsonResponse(
                    500,
                    "application/json",
                    {"success": False, "error": REQUEST_TIMEOUT},
                ),
                PROTOCOL_ERROR_ERROR,
            ),
        ]

        for response, expected in cases:
            with self.subTest(expected=expected):
                router, _ = self.make_router(response)
                result = router.route(self.command("read", "status.read"))
                self.assertFalse(result.success)
                self.assertEqual(expected, result.error)
                self.assertNotIn("http://", str(result.data))

    def test_missing_binding_maps_to_driver_unavailable(self):
        registry = DeviceRegistry()
        device = Device(
            id="lamp_1",
            name="Lamp",
            type="light",
            capabilities=[DeviceCapability(name="status.read", kind="reading")],
        )
        registry.register(device)
        driver = HttpDeviceDriver(HttpDeviceBindingStore(), transport=FakeHttpTransport())
        router = DeviceCommandRouter(registry, driver, DeviceStateCoordinator())

        result = router.route(self.command("read", "status.read"))

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_UNAVAILABLE_ERROR, result.error)
        self.assertEqual("unavailable", result.state.status)

    def test_invalid_capability_stays_router_owned(self):
        response = HttpJsonResponse(
            200,
            "application/json",
            {"success": True, "observations": {"power": True}},
        )
        router, _ = self.make_router(response)

        result = router.route(self.command("read", "legacy.power"))

        self.assertFalse(result.success)
        self.assertEqual("capability_not_found", result.error)


if __name__ == "__main__":
    unittest.main()
