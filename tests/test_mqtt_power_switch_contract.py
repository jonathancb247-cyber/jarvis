"""Focused causality tests for the existing MQTT request/response driver with
the strict power.switch contract.

These tests prove the power.switch causality invariants against
MQTTDeviceDriver using the existing request_id envelope only:

- Only the correlated ESP32-style response may establish the new known state.
- wrong, missing, late, duplicate, and unsolicited request_ids never satisfy
  the active command.
- Semantic state must be exactly the allowed key, a real Python bool, and
  equal to the requested value; anything else fails closed.
- Timeout and malformed responses fail closed; there is no automatic retry.
- One confirmed ExecutionGate execution causes at most one MQTT publish; a
  failed, cancelled, or unconfirmed gate action causes zero publishes.
- Uncertainty demotes a prior known state to stale without fabricating a
  value; a fresh correlated success restores it to known.
- Raw broker/topic/payload internals never leak into the result.
"""

import json
import tempfile
from itertools import count
from pathlib import Path
import unittest

from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
    PLAN_KIND_EXECUTE,
    PLAN_SCHEMA_VERSION,
    AIActionPlan,
    AIActionStep,
)
from jarvis_core.ai.execution_gate import (
    GATE_STATUS_EXECUTED,
    GATE_STATUS_REJECTED,
    REJECT_CONFIRMATION_DIGEST_MISMATCH,
    REJECT_CONFIRMATION_NOT_FOUND,
    ExecutionGate,
)
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    LocalUnderstandingDecision,
)
from jarvis_core.bootstrap import build_runtime_from_profile
from jarvis_core.configuration import RuntimeConfigurationLoader
from jarvis_core.device_routing import (
    INVALID_RESPONSE_ERROR,
    REQUEST_TIMEOUT_ERROR,
    DeviceCommandRouter,
)
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.domain import Command
from jarvis_core.drivers import (
    INVALID_PARAMETERS,
    INVALID_RESPONSE,
    REQUEST_TIMEOUT,
)
from jarvis_core.mqtt_driver import (
    MQTTDeviceBinding,
    MQTTDeviceBindingStore,
    MQTTDeviceDriver,
    MQTTTimeoutError,
)
from jarvis_core.planner import DEVICE_EXECUTE_COMMAND

REQUEST_TOPIC = "jarvis/devices/relay_1/request"
RESPONSE_TOPIC = "jarvis/devices/relay_1/response"


def relay_device(state_status="unknown", state_properties=None):
    return Device(
        id="relay_1",
        name="Relay",
        type="relay",
        capabilities=[
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"type": "string", "required": True}},
            )
        ],
        state=DeviceState(status=state_status, properties=state_properties or {}),
    )


def relay_store():
    store = MQTTDeviceBindingStore()
    store.register(
        MQTTDeviceBinding(
            device_id="relay_1",
            request_topic=REQUEST_TOPIC,
            response_topic=RESPONSE_TOPIC,
            timeout_seconds=2.0,
            allowed_capabilities=("power.switch",),
            allowed_response_keys=("state",),
        )
    )
    return store


def sequential_request_ids():
    counter = count(1)
    return lambda: "req-{}".format(next(counter))


def make_driver(client, request_ids=None):
    if request_ids is None:
        request_ids = lambda: "req-1"
    return MQTTDeviceDriver(
        relay_store(),
        client=client,
        request_id_factory=request_ids,
    )


class ScriptedMQTTClient:
    def __init__(self):
        self.published = []
        self.waits = []
        self.close_count = 0
        self.autorespond = None
        self._responses = {}
        self._errors = {}

    def publish(self, topic, payload):
        self.published.append((topic, payload))
        if self.autorespond is None:
            return
        request = json.loads(payload.decode("utf-8"))
        request_id = request["request_id"]
        if request_id not in self._responses and request_id not in self._errors:
            self._responses[request_id] = self.autorespond(request)

    def wait_for_response(self, topic, correlation_id, timeout_seconds):
        self.waits.append((topic, correlation_id, timeout_seconds))
        if correlation_id in self._errors:
            raise self._errors.pop(correlation_id)
        if correlation_id in self._responses:
            return self._responses.pop(correlation_id)
        raise MQTTTimeoutError()

    def seed(self, correlation_id, response):
        self._responses[correlation_id] = response

    def fail(self, correlation_id, error):
        self._errors[correlation_id] = error

    def close(self):
        self.close_count += 1


def ok_response(correlation_id, state):
    return {
        "request_id": correlation_id,
        "ok": True,
        "semantic": {"state": state},
        "error": None,
    }


class MQTTPowerSwitchContractTests(unittest.TestCase):
    def apply(self, client, parameters, request_ids=None):
        driver = make_driver(client, request_ids=request_ids)
        return driver.apply(relay_device(), "power.switch", parameters)

    def test_valid_apply_uses_existing_envelope_topics_and_one_publish(self):
        client = ScriptedMQTTClient()
        client.seed("req-1", ok_response("req-1", True))

        result = self.apply(client, {"state": "true"})

        self.assertTrue(result.success)
        self.assertEqual({"state": True}, result.observations)
        self.assertEqual(1, len(client.published))
        self.assertEqual((REQUEST_TOPIC, ), (client.published[0][0], ))
        self.assertEqual((RESPONSE_TOPIC, "req-1", 2.0), client.waits[0])
        request = json.loads(client.published[0][1].decode("utf-8"))
        self.assertEqual(
            {
                "request_id": "req-1",
                "device_id": "relay_1",
                "capability": "power.switch",
                "operation": "apply",
                "parameters": {"state": "true"},
            },
            request,
        )

    def test_valid_apply_false_state_succeeds_with_exact_match(self):
        client = ScriptedMQTTClient()
        client.seed("req-1", ok_response("req-1", False))

        result = self.apply(client, {"state": "false"})

        self.assertTrue(result.success)
        self.assertEqual({"state": False}, result.observations)
        self.assertEqual(1, len(client.published))

    def test_wrong_request_id_cannot_satisfy_active_command(self):
        client = ScriptedMQTTClient()
        client.seed("req-1", ok_response("other", True))

        result = self.apply(client, {"state": "true"})

        self.assertFalse(result.success)
        self.assertEqual(INVALID_RESPONSE, result.error)

    def test_missing_request_id_cannot_satisfy_command(self):
        client = ScriptedMQTTClient()
        client.seed(
            "req-1",
            {"ok": True, "semantic": {"state": True}, "error": None},
        )

        result = self.apply(client, {"state": "true"})

        self.assertFalse(result.success)
        self.assertEqual(INVALID_RESPONSE, result.error)

    def test_late_response_from_earlier_request_cannot_satisfy_later(self):
        client = ScriptedMQTTClient()
        request_ids = sequential_request_ids()
        driver = make_driver(client, request_ids=request_ids)
        client.seed("req-1", ok_response("req-1", True))
        first = driver.apply(relay_device(), "power.switch", {"state": "true"})

        client.seed("req-2", ok_response("req-1", True))
        late = driver.apply(relay_device(), "power.switch", {"state": "false"})

        client.seed("req-1", ok_response("req-1", True))
        only_old = driver.apply(relay_device(), "power.switch", {"state": "true"})

        self.assertTrue(first.success)
        self.assertEqual(["req-2", "req-3"], [wait[1] for wait in client.waits[1:]])
        self.assertFalse(late.success)
        self.assertEqual(INVALID_RESPONSE, late.error)
        self.assertFalse(only_old.success)
        self.assertEqual(REQUEST_TIMEOUT, only_old.error)

    def test_duplicate_response_cannot_satisfy_next_command(self):
        client = ScriptedMQTTClient()
        request_ids = sequential_request_ids()
        driver = make_driver(client, request_ids=request_ids)
        client.seed("req-1", ok_response("req-1", True))
        driver.apply(relay_device(), "power.switch", {"state": "true"})

        client.seed("req-2", ok_response("req-1", True))
        next_result = driver.apply(relay_device(), "power.switch", {"state": "true"})

        self.assertFalse(next_result.success)
        self.assertEqual(INVALID_RESPONSE, next_result.error)

    def test_unsolicited_response_without_active_request_id_is_rejected(self):
        client = ScriptedMQTTClient()
        client.seed("req-0", ok_response("req-0", True))

        result = self.apply(client, {"state": "true"})

        self.assertFalse(result.success)
        self.assertEqual(REQUEST_TIMEOUT, result.error)
        self.assertEqual(1, len(client.published))

    def test_mismatched_semantic_state_fails_closed(self):
        cases = [
            ("true", False),
            ("false", True),
            ("true", {"state": False, "extra": 1}),
            ("true", {"power": True}),
        ]

        for requested_state, semantic in cases:
            with self.subTest(semantic=semantic):
                client = ScriptedMQTTClient()
                client.seed(
                    "req-1",
                    {
                        "request_id": "req-1",
                        "ok": True,
                        "semantic": semantic,
                        "error": None,
                    },
                )
                result = self.apply(client, {"state": requested_state})
                self.assertFalse(result.success)
                self.assertEqual(INVALID_RESPONSE, result.error)

    def test_missing_or_non_bool_state_fails_closed(self):
        bad_semantics = [
            {},
            {"state": None},
            {"state": 1},
            {"state": "true"},
            {"state": "1"},
            {"state": "on"},
        ]

        for semantic in bad_semantics:
            with self.subTest(semantic=semantic):
                client = ScriptedMQTTClient()
                client.seed(
                    "req-1",
                    {
                        "request_id": "req-1",
                        "ok": True,
                        "semantic": semantic,
                        "error": None,
                    },
                )
                result = self.apply(client, {"state": "true"})
                self.assertFalse(result.success)
                self.assertEqual(INVALID_RESPONSE, result.error)

    def test_timeout_fails_closed_with_single_publish(self):
        client = ScriptedMQTTClient()
        client.fail("req-1", MQTTTimeoutError())

        result = self.apply(client, {"state": "true"})

        self.assertFalse(result.success)
        self.assertEqual(REQUEST_TIMEOUT, result.error)
        self.assertEqual(1, len(client.published))
        self.assertEqual(1, len(client.waits))

    def test_malformed_response_fails_closed(self):
        malformed = [
            b"{",
            b"[1, 2]",
            {"request_id": "req-1"},
            {"request_id": "req-1", "ok": "yes", "semantic": {}, "error": None},
            {"request_id": "req-1", "ok": True, "semantic": {}, "error": "boom"},
        ]

        for response in malformed:
            with self.subTest(response=response):
                client = ScriptedMQTTClient()
                client.seed("req-1", response)
                driver = make_driver(client)
                result = driver.apply(
                    relay_device(),
                    "power.switch",
                    {"state": "true"},
                )
                self.assertFalse(result.success)
                self.assertEqual(INVALID_RESPONSE, result.error)

    def test_malformed_semantic_shape_fails_closed(self):
        for semantic in [[], "state", 3, True]:
            with self.subTest(semantic=semantic):
                client = ScriptedMQTTClient()
                client.seed(
                    "req-1",
                    {
                        "request_id": "req-1",
                        "ok": True,
                        "semantic": semantic,
                        "error": None,
                    },
                )
                result = self.apply(client, {"state": "true"})
                self.assertFalse(result.success)
                self.assertEqual(INVALID_RESPONSE, result.error)

    def test_no_automatic_mutation_retry(self):
        client = ScriptedMQTTClient()
        client.fail("req-1", MQTTTimeoutError())
        driver = make_driver(client)

        first = driver.apply(relay_device(), "power.switch", {"state": "true"})
        self.assertEqual(1, len(client.published))
        self.assertEqual(1, len(client.waits))
        self.assertFalse(first.success)

        client.fail("req-1", MQTTTimeoutError())
        second = driver.apply(relay_device(), "power.switch", {"state": "true"})
        self.assertEqual(2, len(client.published))
        self.assertEqual(2, len(client.waits))
        self.assertFalse(second.success)

    def test_raw_transport_internals_do_not_leak_into_result(self):
        client = ScriptedMQTTClient()
        client.seed(
            "req-1",
            {
                "request_id": "req-1",
                "ok": True,
                "semantic": {"state": True},
                "error": None,
            },
        )

        result = self.apply(client, {"state": "true"})

        self.assertTrue(result.success)
        self.assertEqual({"state": True}, result.observations)
        for key in ("request_id", "ok", "error", "topic", "payload"):
            self.assertNotIn(key, result.observations)

    def test_invalid_power_switch_parameters_are_rejected_before_publish(self):
        for parameters in [{}, {"state": "on"}, {"state": 1}, {"state": None}]:
            with self.subTest(parameters=parameters):
                client = ScriptedMQTTClient()
                result = self.apply(client, parameters)
                self.assertFalse(result.success)
                self.assertEqual(INVALID_PARAMETERS, result.error)
                self.assertEqual([], client.published)


class MQTTPowerSwitchRouterTests(unittest.TestCase):
    def make_router(self, client, request_ids=None, state_status="unknown", state_properties=None):
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

    def command(self, state):
        return Command(
            name="device.execute",
            args={
                "device_id": "relay_1",
                "capability": "power.switch",
                "operation": "apply",
                "parameters": {"state": state},
            },
            source="test",
        )

    def test_timeout_after_known_marks_state_stale_without_fabricating_value(self):
        client = ScriptedMQTTClient()
        router, registry = self.make_router(
            client,
            request_ids=sequential_request_ids(),
            state_status="known",
            state_properties={"state": False},
        )
        client.fail("req-1", MQTTTimeoutError())

        result = router.route(self.command("true"))

        self.assertFalse(result.success)
        self.assertEqual(REQUEST_TIMEOUT_ERROR, result.error)
        state = registry.get("relay_1").state
        self.assertEqual("stale", state.status)
        self.assertEqual({"state": False}, state.properties)

        client.fail("req-2", MQTTTimeoutError())
        second = router.route(self.command("true"))
        self.assertFalse(second.success)
        state = registry.get("relay_1").state
        self.assertEqual("stale", state.status)
        self.assertEqual({"state": False}, state.properties)

    def test_fresh_successful_correlated_response_restores_known(self):
        client = ScriptedMQTTClient()
        router, registry = self.make_router(
            client,
            request_ids=sequential_request_ids(),
            state_status="known",
            state_properties={"state": False},
        )
        client.seed("req-1", ok_response("req-1", True))

        result = router.route(self.command("true"))

        self.assertTrue(result.success)
        state = registry.get("relay_1").state
        self.assertEqual("known", state.status)
        self.assertEqual({"state": True}, state.properties)

    def test_mismatched_semantic_at_router_fails_closed_without_fabrication(self):
        client = ScriptedMQTTClient()
        router, registry = self.make_router(
            client,
            request_ids=sequential_request_ids(),
            state_status="known",
            state_properties={"state": False},
        )
        client.seed(
            "req-1",
            {
                "request_id": "req-1",
                "ok": True,
                "semantic": {"state": False},
                "error": None,
            },
        )

        result = router.route(self.command("true"))

        self.assertFalse(result.success)
        self.assertEqual(INVALID_RESPONSE_ERROR, result.error)
        state = registry.get("relay_1").state
        self.assertEqual("stale", state.status)
        self.assertEqual({"state": False}, state.properties)


def executable_power_switch_decision(command):
    return LocalUnderstandingDecision(
        provider_id="causality-test",
        model_id="causality-test",
        status=EXECUTABLE_CANDIDATE,
        proposal_valid=True,
        resolver_kind=PLAN_KIND_EXECUTE,
        planner_kind=DEVICE_EXECUTE_COMMAND,
        confirmation_required=True,
        plan=AIActionPlan(
            schema_version=PLAN_SCHEMA_VERSION,
            kind=PLAN_KIND_EXECUTE,
            steps=(
                AIActionStep(
                    index=0,
                    canonical_command_text=command,
                    safe_description="Prepared power.switch on relay_1.",
                    target_device_id="relay_1",
                    capability_name="power.switch",
                    action_kind=ACTION_KIND_MUTATE,
                    requires_confirmation=True,
                    policy_flags=("device_mutation", "requires_confirmation"),
                ),
            ),
            safe_summary="Prepared a deterministic device plan.",
            confirmation_required=True,
            policy_flags=("device_mutation", "requires_confirmation"),
        ),
        commands_executed=False,
    )


def write_power_switch_profile(root):
    profile_path = Path(root) / "mqtt-power-switch.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "profile": "mqtt-power-switch",
                "devices": [
                    {
                        "id": "relay_1",
                        "name": "Relay",
                        "type": "relay",
                        "capabilities": [
                            {
                                "name": "power.switch",
                                "kind": "action",
                                "parameters": {
                                    "state": {"type": "string", "required": True}
                                },
                                "constraints": {},
                                "availability_policy": {},
                            }
                        ],
                        "metadata": {},
                    }
                ],
                "http_bindings": [],
                "mqtt_bindings": [
                    {
                        "transport": "mqtt",
                        "device_id": "relay_1",
                        "request_topic": REQUEST_TOPIC,
                        "response_topic": RESPONSE_TOPIC,
                        "timeout_seconds": 2.0,
                        "allowed_capabilities": ["power.switch"],
                        "allowed_response_keys": ["state"],
                    }
                ],
                "runtime_options": {},
            }
        ),
        encoding="utf-8",
    )
    return profile_path


class MQTTPowerSwitchGateTests(unittest.TestCase):
    def build_runtime(self, root, client):
        profile = RuntimeConfigurationLoader().load(
            write_power_switch_profile(root)
        )
        return build_runtime_from_profile(
            profile,
            mqtt_client=client,
            base_directory=root,
        )

    def test_one_confirmed_execution_causes_at_most_one_mqtt_publish(self):
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

    def test_unconfirmed_gate_action_produces_zero_mqtt_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = ScriptedMQTTClient()
            client.autorespond = lambda request: ok_response(
                request["request_id"], True
            )
            runtime = self.build_runtime(root, client)
            gate = ExecutionGate(runtime)

            gate.prepare(
                executable_power_switch_decision(
                    "device apply relay_1 power.switch state=true"
                )
            )

            self.assertEqual([], client.published)

    def test_rejected_gate_action_produces_zero_mqtt_publishes(self):
        scenarios = [
            ("wrong_id", lambda gate, prepared: gate.confirm(
                "not-the-confirmation-id", prepared.plan_digest
            )),
            ("wrong_digest", lambda gate, prepared: gate.confirm(
                prepared.confirmation_id, "0" * 64
            )),
        ]
        for label, act in scenarios:
            with self.subTest(label=label):
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

                    result = act(gate, prepared)

                    self.assertEqual(GATE_STATUS_REJECTED, result.status)
                    self.assertEqual([], client.published)


if __name__ == "__main__":
    unittest.main()