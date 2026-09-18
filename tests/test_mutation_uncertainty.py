"""Cross-driver mutation-uncertainty regression battery.

Pins the transport-neutral uncertainty contract on the DriverBoundary:

- ``DriverResult.mutation_uncertain`` defaults to False (deterministic).
- A failed ``apply`` result demotes a prior known state to stale ONLY when a
  driver explicitly marks ``mutation_uncertain=True`` because dispatch may
  have occurred.
- Deterministic pre-dispatch failures (invalid parameters, missing binding,
  invalid configuration) preserve the previous known/current state untouched.
- Every built-in driver must keep pre-dispatch failures deterministic and mark
  only genuinely ambiguous post-dispatch failures as uncertain.
"""

import tempfile
from pathlib import Path
import unittest

from jarvis_core.ai.execution_gate import (
    GATE_STATUS_EXECUTED,
    GATE_STATUS_REJECTED,
    ExecutionGate,
)
from jarvis_core.bootstrap import build_runtime_from_profile
from jarvis_core.configuration import RuntimeConfigurationLoader
from jarvis_core.device_routing import (
    CONFIGURATION_INVALID_ERROR,
    DRIVER_UNAVAILABLE_ERROR,
    INVALID_PARAMETERS_ERROR,
    INVALID_RESPONSE_ERROR,
    REQUEST_TIMEOUT_ERROR,
    DeviceCommandRouter,
)
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.driver_selection import DeviceTransportDriver
from jarvis_core.drivers import (
    CONFIGURATION_INVALID,
    INVALID_PARAMETERS,
    SimulatedDriver,
)
from jarvis_core.domain import Command
from jarvis_core.http_driver import (
    HttpDeviceBinding,
    HttpDeviceBindingStore,
    HttpDeviceDriver,
    HttpTimeoutError,
)
from jarvis_core.mqtt_driver import MQTTTimeoutError

from tests.test_http_device_driver import FakeHttpTransport
from tests.test_mqtt_power_switch_contract import (
    REQUEST_TOPIC,
    ScriptedMQTTClient,
    executable_power_switch_decision,
    make_driver,
    ok_response,
    relay_device,
    sequential_request_ids,
    write_power_switch_profile,
)


def power_driver_device(state_status="unknown", state_properties=None):
    return Device(
        id="relay_1",
        name="Relay",
        type="relay",
        capabilities=[
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"type": "string", "required": True}},
            ),
            DeviceCapability(name="power.set", kind="action"),
            DeviceCapability(name="status.read", kind="reading"),
        ],
        state=DeviceState(status=state_status, properties=state_properties or {}),
    )


def apply_command(parameters=None, capability="power.switch"):
    return Command(
        name="device.execute",
        args={
            "device_id": "relay_1",
            "capability": capability,
            "operation": "apply",
            "parameters": parameters if parameters is not None else {"state": "true"},
        },
        source="test",
    )


def register(device):
    registry = DeviceRegistry()
    registry.register(device)
    return registry


def mqtt_router(client, request_ids=None, state_status="unknown", state_properties=None):
    registry = DeviceRegistry()
    registry.register(
        relay_device(
            state_status=state_status,
            state_properties=state_properties,
        )
    )
    driver = make_driver(client, request_ids=request_ids)
    router = DeviceCommandRouter(registry, driver, DeviceStateCoordinator())
    return router, registry


class CrossDriverUncertaintyTests(unittest.TestCase):
    def test_simulated_invalid_parameters_after_known_preserves_known(self):
        device = power_driver_device(
            state_status="known",
            state_properties={"power": True},
        )
        registry = register(device)
        result = SimulatedDriver().apply(device, "power.set", "not-a-dict")
        self.assertFalse(result.success)
        self.assertEqual(INVALID_PARAMETERS, result.error)

        state = DeviceStateCoordinator().coordinate(
            device,
            "power.set",
            "apply",
            result,
            registry,
        )

        self.assertIs(device.state, state)
        self.assertEqual("known", state.status)
        self.assertEqual({"power": True}, state.properties)

    def test_missing_transport_binding_after_known_preserves_known(self):
        device = power_driver_device(
            state_status="known",
            state_properties={"power": True},
        )
        registry = register(device)
        router = DeviceCommandRouter(
            registry,
            DeviceTransportDriver(),
            DeviceStateCoordinator(),
        )
        before = registry.get("relay_1").state

        result = router.route(apply_command())

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_UNAVAILABLE_ERROR, result.error)
        self.assertIs(before, registry.get("relay_1").state)
        self.assertEqual("known", registry.get("relay_1").state.status)
        self.assertEqual({"power": True}, registry.get("relay_1").state.properties)

    def test_http_invalid_configuration_after_known_preserves_known(self):
        store = HttpDeviceBindingStore()
        store.register(HttpDeviceBinding("relay_1", "http://localhost:8000"))
        transport = FakeHttpTransport()
        driver = HttpDeviceDriver(store, transport=transport)
        device = power_driver_device(
            state_status="known",
            state_properties={"power": True},
        )
        registry = register(device)
        result = driver.apply(device, "power.switch", "not-a-dict")
        self.assertFalse(result.success)
        self.assertEqual(CONFIGURATION_INVALID, result.error)
        self.assertEqual([], transport.calls)

        state = DeviceStateCoordinator().coordinate(
            device,
            "power.switch",
            "apply",
            result,
            registry,
        )

        self.assertIs(device.state, state)
        self.assertEqual("known", state.status)
        self.assertEqual({"power": True}, state.properties)

    def test_http_missing_binding_after_known_preserves_known(self):
        device = power_driver_device(
            state_status="known",
            state_properties={"power": True},
        )
        registry = register(device)
        transport = FakeHttpTransport()
        driver = HttpDeviceDriver(HttpDeviceBindingStore(), transport=transport)
        router = DeviceCommandRouter(registry, driver, DeviceStateCoordinator())
        before = registry.get("relay_1").state

        result = router.route(apply_command())

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_UNAVAILABLE_ERROR, result.error)
        self.assertEqual([], transport.calls)
        self.assertIs(before, registry.get("relay_1").state)
        self.assertEqual("known", registry.get("relay_1").state.status)
        self.assertEqual({"power": True}, registry.get("relay_1").state.properties)

    def test_http_timeout_after_dispatch_marks_state_stale(self):
        store = HttpDeviceBindingStore()
        store.register(HttpDeviceBinding("relay_1", "http://localhost:8000"))
        transport = FakeHttpTransport(error=HttpTimeoutError())
        driver = HttpDeviceDriver(store, transport=transport)
        device = power_driver_device(
            state_status="known",
            state_properties={"power": True},
        )
        registry = register(device)
        router = DeviceCommandRouter(registry, driver, DeviceStateCoordinator())

        result = router.route(apply_command())

        self.assertFalse(result.success)
        self.assertEqual(REQUEST_TIMEOUT_ERROR, result.error)
        self.assertEqual(1, len(transport.calls))
        state = registry.get("relay_1").state
        self.assertEqual("stale", state.status)
        self.assertEqual({"power": True}, state.properties)

    def test_mqtt_timeout_after_publish_marks_state_stale(self):
        client = ScriptedMQTTClient()
        client.fail("req-1", MQTTTimeoutError())
        router, registry = mqtt_router(
            client,
            request_ids=sequential_request_ids(),
            state_status="known",
            state_properties={"state": False},
        )

        result = router.route(apply_command())

        self.assertFalse(result.success)
        self.assertEqual(REQUEST_TIMEOUT_ERROR, result.error)
        self.assertEqual(1, len(client.published))
        self.assertEqual(REQUEST_TOPIC, client.published[0][0])
        state = registry.get("relay_1").state
        self.assertEqual("stale", state.status)
        self.assertEqual({"state": False}, state.properties)

    def test_mqtt_malformed_ack_after_publish_marks_state_stale(self):
        client = ScriptedMQTTClient()
        client.seed("req-1", b"{")
        router, registry = mqtt_router(
            client,
            request_ids=sequential_request_ids(),
            state_status="known",
            state_properties={"state": False},
        )

        result = router.route(apply_command())

        self.assertFalse(result.success)
        self.assertEqual(INVALID_RESPONSE_ERROR, result.error)
        self.assertEqual(1, len(client.published))
        state = registry.get("relay_1").state
        self.assertEqual("stale", state.status)
        self.assertEqual({"state": False}, state.properties)

    def test_unknown_with_deterministic_failure_preserves_unknown(self):
        device = power_driver_device()
        registry = register(device)
        result = SimulatedDriver().apply(device, "power.set", "not-a-dict")

        state = DeviceStateCoordinator().coordinate(
            device,
            "power.set",
            "apply",
            result,
            registry,
        )

        self.assertIs(device.state, state)
        self.assertEqual("unknown", state.status)

    def test_fresh_success_after_stale_restores_known(self):
        client = ScriptedMQTTClient()
        client.fail("req-1", MQTTTimeoutError())
        router, registry = mqtt_router(
            client,
            request_ids=sequential_request_ids(),
            state_status="known",
            state_properties={"state": False},
        )

        first = router.route(apply_command())
        self.assertFalse(first.success)
        self.assertEqual("stale", registry.get("relay_1").state.status)

        client.seed("req-2", ok_response("req-2", True))
        second = router.route(apply_command())

        self.assertTrue(second.success)
        state = registry.get("relay_1").state
        self.assertEqual("known", state.status)
        self.assertEqual({"state": True}, state.properties)


class CrossDriverUncertaintyGateTests(unittest.TestCase):
    def build_runtime(self, root, client):
        profile = RuntimeConfigurationLoader().load(
            write_power_switch_profile(root)
        )
        return build_runtime_from_profile(
            profile,
            mqtt_client=client,
            base_directory=root,
        )

    def test_confirmed_execution_single_mqtt_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = ScriptedMQTTClient()
            client.autorespond = lambda request: ok_response(
                request["request_id"], True
            )
            runtime = self.build_runtime(root, client)
            gate = ExecutionGate(runtime)
            prepared = gate.prepare(
                executable_power_switch_decision(
                    "device apply relay_1 power.switch state=true"
                )
            )

            result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

            self.assertEqual(GATE_STATUS_EXECUTED, result.status)
            self.assertTrue(result.success)
            self.assertEqual(1, len(client.published))
            self.assertEqual(1, len(client.waits))
            self.assertEqual(REQUEST_TOPIC, client.published[0][0])
            state = runtime.context.device_registry.get("relay_1").state
            self.assertEqual("known", state.status)
            self.assertEqual({"state": True}, state.properties)

    def test_rejected_confirmation_zero_mqtt_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = ScriptedMQTTClient()
            client.autorespond = lambda request: ok_response(
                request["request_id"], True
            )
            runtime = self.build_runtime(root, client)
            gate = ExecutionGate(runtime)
            prepared = gate.prepare(
                executable_power_switch_decision(
                    "device apply relay_1 power.switch state=true"
                )
            )

            result = gate.confirm("not-the-confirmation-id", prepared.plan_digest)

            self.assertEqual(GATE_STATUS_REJECTED, result.status)
            self.assertEqual([], client.published)


if __name__ == "__main__":
    unittest.main()