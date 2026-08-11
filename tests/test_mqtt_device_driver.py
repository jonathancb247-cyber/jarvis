import json
import unittest

from jarvis_core.device_routing import (
    CONNECTION_FAILED_ERROR,
    DRIVER_UNAVAILABLE_ERROR,
    INVALID_RESPONSE_ERROR,
    OPERATION_NOT_SUPPORTED_ERROR,
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
    REQUEST_TIMEOUT,
)
from jarvis_core.mqtt_driver import (
    MQTTPublishError,
    MQTTClientClosedError,
    MQTTConnectionError,
    MQTTDeviceBinding,
    MQTTDeviceBindingStore,
    MQTTDeviceDriver,
    MQTTResponseTooLargeError,
    MQTTTimeoutError,
)


class FakeMQTTClient:
    def __init__(self, response=None, wait_error=None, publish_error=None):
        self.response = response or {
            "request_id": "req-1",
            "ok": True,
            "semantic": {"power": True},
            "error": None,
        }
        self.wait_error = wait_error
        self.publish_error = publish_error
        self.published = []
        self.waits = []
        self.close_count = 0

    def publish(self, topic, payload):
        self.published.append((topic, payload))
        if self.publish_error:
            raise self.publish_error

    def wait_for_response(self, topic, correlation_id, timeout_seconds):
        self.waits.append((topic, correlation_id, timeout_seconds))
        if self.wait_error:
            raise self.wait_error
        if isinstance(self.response, dict):
            response = self.response.copy()
            if response.get("request_id") == "req-1":
                response["request_id"] = correlation_id
            return response
        return self.response

    def close(self):
        self.close_count += 1


class MQTTDeviceDriverTests(unittest.TestCase):
    def make_device(self):
        return Device(
            id="sensor_1",
            name="Room Sensor",
            type="sensor",
            capabilities=[
                DeviceCapability(name="temperature.read", kind="reading"),
                DeviceCapability(
                    name="power.switch",
                    kind="action",
                    parameters={"state": {"type": "string", "required": True}},
                ),
            ],
            state=DeviceState(status="unknown", properties={}),
        )

    def make_driver(self, response=None, wait_error=None, publish_error=None):
        store = MQTTDeviceBindingStore()
        binding = MQTTDeviceBinding(
            device_id="sensor_1",
            request_topic="jarvis/devices/sensor_1/request",
            response_topic="jarvis/devices/sensor_1/response",
            timeout_seconds=2.0,
            allowed_capabilities=("temperature.read", "power.switch"),
            allowed_response_keys=("temperature", "power"),
        )
        store.register(binding)
        client = FakeMQTTClient(
            response=response,
            wait_error=wait_error,
            publish_error=publish_error,
        )
        driver = MQTTDeviceDriver(
            store,
            client=client,
            request_id_factory=lambda: "req-1",
        )
        return driver, client

    def test_binding_rejects_invalid_topics_and_wildcards(self):
        cases = [
            "jarvis/#",
            "jarvis/+/request",
            "jarvis/\x01/request",
            "",
            " topic",
        ]

        for topic in cases:
            with self.subTest(topic=repr(topic)):
                with self.assertRaises(ValueError):
                    MQTTDeviceBinding(
                        device_id="sensor_1",
                        request_topic=topic,
                        response_topic="jarvis/devices/sensor_1/response",
                        allowed_capabilities=("temperature.read",),
                        allowed_response_keys=("temperature",),
                    )

    def test_read_success_publishes_bounded_request_and_returns_semantic_result(self):
        driver, client = self.make_driver(
            response={
                "request_id": "req-1",
                "ok": True,
                "semantic": {"temperature": 24.5},
                "error": None,
            }
        )

        result = driver.read(self.make_device(), "temperature.read")

        self.assertTrue(result.success)
        self.assertEqual({"temperature": 24.5}, result.observations)
        self.assertEqual("jarvis/devices/sensor_1/request", client.published[0][0])
        request = json.loads(client.published[0][1].decode("utf-8"))
        self.assertEqual(
            {
                "request_id": "req-1",
                "device_id": "sensor_1",
                "capability": "temperature.read",
                "operation": "read",
                "parameters": {},
            },
            request,
        )
        self.assertEqual(("jarvis/devices/sensor_1/response", "req-1", 2.0), client.waits[0])

    def test_apply_success_uses_same_request_response_boundary(self):
        driver, client = self.make_driver(
            response={
                "request_id": "req-1",
                "ok": True,
                "semantic": {"power": True},
                "error": None,
            }
        )

        result = driver.apply(self.make_device(), "power.switch", {"state": "true"})

        self.assertTrue(result.success)
        self.assertEqual({"power": True}, result.observations)
        request = json.loads(client.published[0][1].decode("utf-8"))
        self.assertEqual("apply", request["operation"])
        self.assertEqual({"state": "true"}, request["parameters"])

    def test_response_validation_rejects_mismatches_unknown_fields_and_semantic_keys(self):
        cases = [
            (
                {
                    "request_id": "other",
                    "ok": True,
                    "semantic": {"temperature": 24},
                    "error": None,
                },
                INVALID_RESPONSE,
            ),
            (
                {
                    "request_id": "req-1",
                    "ok": True,
                    "semantic": {"temperature": 24},
                    "error": None,
                    "debug": "raw broker trace",
                },
                INVALID_RESPONSE,
            ),
            (
                {
                    "request_id": "req-1",
                    "ok": True,
                    "semantic": {"raw_payload": "secret"},
                    "error": None,
                },
                INVALID_RESPONSE,
            ),
        ]

        for response, expected in cases:
            with self.subTest(response=response):
                driver, _ = self.make_driver(response=response)
                result = driver.read(self.make_device(), "temperature.read")
                self.assertFalse(result.success)
                self.assertEqual(expected, result.error)

    def test_duplicate_and_late_responses_are_not_persisted_by_driver(self):
        driver, client = self.make_driver(
            response={
                "request_id": "req-1",
                "ok": True,
                "semantic": {"temperature": 20},
                "error": None,
            }
        )

        first = driver.read(self.make_device(), "temperature.read")
        second = driver.read(self.make_device(), "temperature.read")

        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(2, len(client.waits))
        self.assertEqual(2, len(client.published))

    def test_timeout_publish_broker_and_shutdown_errors_are_normalized(self):
        cases = [
            (None, MQTTTimeoutError(), REQUEST_TIMEOUT),
            (None, MQTTConnectionError(), CONNECTION_FAILED),
            (MQTTPublishError(), None, CONNECTION_FAILED),
            (None, MQTTClientClosedError(), CONNECTION_FAILED),
            (None, MQTTResponseTooLargeError(), INVALID_RESPONSE),
        ]

        for publish_error, wait_error, expected in cases:
            with self.subTest(expected=expected):
                driver, _ = self.make_driver(
                    wait_error=wait_error,
                    publish_error=publish_error,
                )
                result = driver.read(self.make_device(), "temperature.read")
                self.assertFalse(result.success)
                self.assertEqual(expected, result.error)

    def test_malformed_and_oversized_responses_are_rejected(self):
        driver, _ = self.make_driver(response=b"{")
        malformed = driver.read(self.make_device(), "temperature.read")
        self.assertFalse(malformed.success)
        self.assertEqual(INVALID_RESPONSE, malformed.error)

        driver, _ = self.make_driver(response=b" " * 10)
        driver.max_response_bytes = 1
        oversized = driver.read(self.make_device(), "temperature.read")
        self.assertFalse(oversized.success)
        self.assertEqual(INVALID_RESPONSE, oversized.error)

    def test_remote_errors_are_safely_mapped(self):
        cases = [
            (REQUEST_TIMEOUT, REQUEST_TIMEOUT),
            (DRIVER_UNAVAILABLE, DRIVER_UNAVAILABLE),
            (OPERATION_NOT_SUPPORTED, OPERATION_NOT_SUPPORTED),
            ("stack trace with broker host", "protocol_error"),
        ]

        for remote_error, expected in cases:
            with self.subTest(remote_error=remote_error):
                driver, _ = self.make_driver(
                    response={
                        "request_id": "req-1",
                        "ok": False,
                        "semantic": {},
                        "error": remote_error,
                    }
                )
                result = driver.read(self.make_device(), "temperature.read")
                self.assertFalse(result.success)
                self.assertEqual(expected, result.error)

    def test_unsupported_capability_does_not_publish(self):
        driver, client = self.make_driver()

        result = driver.read(self.make_device(), "humidity.read")

        self.assertFalse(result.success)
        self.assertEqual(OPERATION_NOT_SUPPORTED, result.error)
        self.assertEqual([], client.published)

    def test_driver_does_not_mutate_device_state_or_write_persistence(self):
        device = self.make_device()
        before = device.state
        driver, _ = self.make_driver()

        result = driver.read(device, "temperature.read")

        self.assertTrue(result.success)
        self.assertIs(before, device.state)

    def test_close_delegates_to_client_without_exposing_errors(self):
        driver, client = self.make_driver()

        driver.close()

        self.assertEqual(1, client.close_count)


class MQTTDeviceRouterIntegrationTests(unittest.TestCase):
    def make_router(self, response=None, wait_error=None):
        registry = DeviceRegistry()
        device = Device(
            id="sensor_1",
            name="Room Sensor",
            type="sensor",
            capabilities=[
                DeviceCapability(name="temperature.read", kind="reading"),
                DeviceCapability(
                    name="power.switch",
                    kind="action",
                    parameters={"state": {"type": "string", "required": True}},
                ),
            ],
            state=DeviceState(status="unknown", properties={}),
        )
        registry.register(device)
        store = MQTTDeviceBindingStore()
        store.register(
            MQTTDeviceBinding(
                device_id="sensor_1",
                request_topic="jarvis/devices/sensor_1/request",
                response_topic="jarvis/devices/sensor_1/response",
                allowed_capabilities=("temperature.read", "power.switch"),
                allowed_response_keys=("temperature", "power"),
            )
        )
        driver = MQTTDeviceDriver(
            store,
            client=FakeMQTTClient(response=response, wait_error=wait_error),
            request_id_factory=lambda: "req-1",
        )
        return DeviceCommandRouter(registry, driver, DeviceStateCoordinator()), registry

    def command(self, operation, capability, parameters=None):
        return Command(
            name="device.execute",
            args={
                "device_id": "sensor_1",
                "capability": capability,
                "operation": operation,
                "parameters": parameters or {},
            },
            source="test",
        )

    def test_successful_mqtt_result_updates_state_through_coordinator(self):
        router, registry = self.make_router(
            response={
                "request_id": "req-1",
                "ok": True,
                "semantic": {"temperature": 23},
                "error": None,
            }
        )

        result = router.route(self.command("read", "temperature.read"))

        self.assertTrue(result.success)
        self.assertEqual("known", result.state.status)
        self.assertEqual({"temperature": 23}, registry.get("sensor_1").state.properties)

    def test_failed_mqtt_result_does_not_create_false_known_state(self):
        router, registry = self.make_router(wait_error=MQTTTimeoutError())

        result = router.route(self.command("read", "temperature.read"))

        self.assertFalse(result.success)
        self.assertEqual(REQUEST_TIMEOUT_ERROR, result.error)
        self.assertEqual("unknown", registry.get("sensor_1").state.status)

    def test_router_maps_mqtt_driver_errors_safely(self):
        cases = [
            (MQTTConnectionError(), CONNECTION_FAILED_ERROR),
            (MQTTTimeoutError(), REQUEST_TIMEOUT_ERROR),
        ]

        for error, expected in cases:
            with self.subTest(expected=expected):
                router, _ = self.make_router(wait_error=error)
                result = router.route(self.command("read", "temperature.read"))
                self.assertFalse(result.success)
                self.assertEqual(expected, result.error)

    def test_missing_mqtt_binding_maps_to_driver_unavailable(self):
        store = MQTTDeviceBindingStore()
        driver = MQTTDeviceDriver(store, client=FakeMQTTClient())
        registry = DeviceRegistry()
        registry.register(
            Device(
                id="sensor_1",
                name="Room Sensor",
                type="sensor",
                capabilities=[DeviceCapability(name="temperature.read", kind="reading")],
            )
        )
        router = DeviceCommandRouter(registry, driver, DeviceStateCoordinator())

        result = router.route(self.command("read", "temperature.read"))

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_UNAVAILABLE_ERROR, result.error)

    def test_invalid_response_maps_without_raw_payload_leak(self):
        router, _ = self.make_router(
            response={
                "request_id": "other",
                "ok": True,
                "semantic": {"raw_payload": "secret"},
                "error": None,
            }
        )

        result = router.route(self.command("read", "temperature.read"))

        self.assertFalse(result.success)
        self.assertEqual(INVALID_RESPONSE_ERROR, result.error)
        self.assertNotIn("secret", str(result.data))


if __name__ == "__main__":
    unittest.main()
