"""Tests for the thesis-only guarded MQTT pilot tool.

These tests use real JarvisOS resolver, ExecutionGate, Runtime,
DeviceRuntimeCapability and EventBus, with fake routers and fake MQTT clients.
They never touch the network, a broker, MQTT deployment configuration, the
State Store, firmware or hardware.
"""

from __future__ import annotations

import json
import paho.mqtt.client as paho_mqtt
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from jarvis_core.capabilities.device import DeviceRuntimeCapability
from jarvis_core.device_routing import (
    REQUEST_TIMEOUT_ERROR,
    DeviceCommandRouter,
    DeviceExecutionResult,
)
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import (
    Device,
    DeviceCapability,
    DeviceRegistry,
    DeviceState,
)
from jarvis_core.driver_selection import DeviceTransportDriver
from jarvis_core.domain import RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.mqtt_driver import (
    MQTTDeviceBinding,
    MQTTDeviceBindingStore,
    MQTTDeviceDriver,
    MQTTTimeoutError,
    UnavailableMQTTClient,
)
from jarvis_core.mqtt_paho import PahoMQTTClient
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.runtime import (
    CAPABILITY_EXECUTION_COMPLETED_EVENT,
    CAPABILITY_EXECUTION_FAILED_EVENT,
    COMMAND_EXECUTION_STARTED_EVENT,
    Runtime,
)

from tools import run_guarded_hardware_validation as guarded
from tools import run_thesis_mqtt_pilot as pilot


DEVICE_ID = "relay_1"
CAPABILITY = "power.switch"


def _device():
    return Device(
        id=DEVICE_ID,
        name="Relay",
        type="light",
        capabilities=[
            DeviceCapability(
                name=CAPABILITY,
                kind="action",
                parameters={"state": {"type": "string", "required": True}},
            )
        ],
    )


class FakeRouter:
    def __init__(self, succeed=True):
        self.calls = []
        self.succeed = succeed

    def route(self, command):
        self.calls.append(command)
        if self.succeed:
            return DeviceExecutionResult(
                True,
                DEVICE_ID,
                CAPABILITY,
                "apply",
                state=DeviceState(status="known", properties={"state": True}),
            )
        return DeviceExecutionResult(
            False,
            DEVICE_ID,
            CAPABILITY,
            "apply",
            state=None,
            error=REQUEST_TIMEOUT_ERROR,
        )


class FakeClient:
    def __init__(self, response=b"{}", error=None):
        self.published = []
        self.waited = []
        self.closed = False
        self._response = response
        self._error = error

    def publish(self, topic, payload):
        self.published.append((topic, payload))

    def wait_for_response(self, topic, correlation_id, timeout_seconds):
        self.waited.append((topic, correlation_id, timeout_seconds))
        if self._error is not None:
            raise self._error
        return self._response

    def close(self):
        self.closed = True


def make_harness(succeed=True):
    bus = EventBus()
    device_registry = DeviceRegistry()
    device_registry.register(_device())
    capability_registry = CapabilityRegistry()
    router = FakeRouter(succeed)
    capability_registry.register(
        DeviceRuntimeCapability.name, DeviceRuntimeCapability(router)
    )
    context = RuntimeContext(
        event_bus=bus,
        capability_registry=capability_registry,
        device_registry=device_registry,
    )
    runtime = Runtime(Planner(), context)
    evidence = guarded.Evidence()
    harness = guarded.GuardedHardwareValidation(runtime, evidence)
    return harness, runtime, router, evidence, bus


def make_observer_runtime():
    bus = EventBus()
    device_registry = DeviceRegistry()
    device_registry.register(_device())
    store = MQTTDeviceBindingStore()
    store.register(
        MQTTDeviceBinding(
            device_id=DEVICE_ID,
            request_topic="jarvis/request",
            response_topic="jarvis/response",
            allowed_capabilities=(CAPABILITY,),
            allowed_response_keys=("state",),
        )
    )
    client = FakeClient()
    mqtt_driver = MQTTDeviceDriver(store, client=client)
    transport = DeviceTransportDriver()
    transport.register(DEVICE_ID, mqtt_driver)
    router = DeviceCommandRouter(
        device_registry, transport, DeviceStateCoordinator()
    )
    capability_registry = CapabilityRegistry()
    capability_registry.register(
        DeviceRuntimeCapability.name, DeviceRuntimeCapability(router)
    )
    context = RuntimeContext(
        event_bus=bus,
        capability_registry=capability_registry,
        device_registry=device_registry,
    )
    return Runtime(Planner(), context), mqtt_driver, client


def make_fault_runtime(*, response=None, error=None, request_id="req-fixed"):
    """Build a guarded MQTT harness with a deterministic request_id factory."""
    bus = EventBus()
    device_registry = DeviceRegistry()
    device_registry.register(_device())
    store = MQTTDeviceBindingStore()
    store.register(
        MQTTDeviceBinding(
            device_id=DEVICE_ID,
            request_topic="jarvis/request",
            response_topic="jarvis/response",
            allowed_capabilities=(CAPABILITY,),
            allowed_response_keys=("state",),
        )
    )
    client = FakeClient(
        response=b"{}" if response is None else response, error=error
    )
    mqtt_driver = MQTTDeviceDriver(
        store, client=client, request_id_factory=lambda: request_id
    )
    transport = DeviceTransportDriver()
    transport.register(DEVICE_ID, mqtt_driver)
    router = DeviceCommandRouter(
        device_registry, transport, DeviceStateCoordinator()
    )
    capability_registry = CapabilityRegistry()
    capability_registry.register(
        DeviceRuntimeCapability.name, DeviceRuntimeCapability(router)
    )
    context = RuntimeContext(
        event_bus=bus,
        capability_registry=capability_registry,
        device_registry=device_registry,
    )
    runtime = Runtime(Planner(), context)
    evidence = guarded.Evidence()
    harness = guarded.GuardedHardwareValidation(runtime, evidence)
    return harness, runtime, mqtt_driver, client, bus


def make_broker_runtime(client):
    """Build a guarded MQTT runtime with an explicit composed client."""
    bus = EventBus()
    device_registry = DeviceRegistry()
    device_registry.register(_device())
    store = MQTTDeviceBindingStore()
    store.register(
        MQTTDeviceBinding(
            device_id=DEVICE_ID,
            request_topic="jarvis/request",
            response_topic="jarvis/response",
            allowed_capabilities=(CAPABILITY,),
            allowed_response_keys=("state",),
        )
    )
    mqtt_driver = MQTTDeviceDriver(store, client=client)
    transport = DeviceTransportDriver()
    transport.register(DEVICE_ID, mqtt_driver)
    router = DeviceCommandRouter(
        device_registry, transport, DeviceStateCoordinator()
    )
    capability_registry = CapabilityRegistry()
    capability_registry.register(
        DeviceRuntimeCapability.name, DeviceRuntimeCapability(router)
    )
    context = RuntimeContext(
        event_bus=bus,
        capability_registry=capability_registry,
        device_registry=device_registry,
    )
    return Runtime(Planner(), context), mqtt_driver


def valid_response(request_id, state):
    return json.dumps(
        {
            "request_id": request_id,
            "ok": True,
            "semantic": {"state": state},
            "error": None,
        }
    ).encode("utf-8")


def single_spec(requested_state):
    return [pilot.TrialSpec(1, 1, requested_state)]


def run_campaign(
    harness,
    bus,
    out_dir,
    *,
    dry_run,
    confirm=True,
    observe="on",
    specs=None,
    observer_status=pilot.MQTT_OBSERVER_NOT_ATTACHED,
    fault_case=pilot.DEFAULT_FAULT_CASE,
    late_response=None,
):
    hub = pilot.TimingHub()
    timer = pilot.EventTimer(hub)
    for event_type in (
        COMMAND_EXECUTION_STARTED_EVENT,
        CAPABILITY_EXECUTION_COMPLETED_EVENT,
        CAPABILITY_EXECUTION_FAILED_EVENT,
    ):
        bus.subscribe(event_type, timer)
    if observer_status == pilot.MQTT_OBSERVER_ATTACHED:
        observer_status = pilot.attach_mqtt_observer(harness.runtime, hub)
    campaign = pilot.PilotCampaign(
        harness=harness,
        hub=hub,
        out_dir=Path(out_dir),
        specs=specs if specs is not None else pilot.build_trial_specs(1),
        dry_run=dry_run,
        confirm_fn=lambda: confirm,
        observe_fn=lambda: observe,
        mqtt_observer_status=observer_status,
        verbose=False,
        fault_case=fault_case,
        late_response=late_response,
    )
    summary = campaign.run()
    return campaign, summary


class TrialPlanningTests(unittest.TestCase):
    def test_pairs_alternate_off_on(self):
        specs = pilot.build_trial_specs(3)
        self.assertEqual(
            [spec.requested_state for spec in specs],
            ["off", "on", "off", "on", "off", "on"],
        )
        self.assertEqual([spec.pair_index for spec in specs], [1, 1, 2, 2, 3, 3])
        self.assertEqual(specs[0].sequence_position, "first")
        self.assertEqual(specs[1].sequence_position, "second")
        self.assertEqual(specs[0].request, guarded.REQUEST_OFF)
        self.assertEqual(specs[1].request, guarded.REQUEST_ON)
        self.assertEqual(specs[0].hint_state, guarded.STATE_FALSE)
        self.assertEqual(specs[1].hint_state, guarded.STATE_TRUE)


class ObservedMqttClientTests(unittest.TestCase):
    def test_delegates_and_marks(self):
        hub = pilot.TimingHub()
        hub.begin()
        inner = FakeClient(response=b"payload")
        observed = pilot.ObservedMqttClient(inner, hub)

        observed.publish("topic", b"data")
        response = observed.wait_for_response("topic", "cid", 1.0)

        self.assertEqual(response, b"payload")
        self.assertEqual(inner.published, [("topic", b"data")])
        self.assertEqual(inner.waited, [("topic", "cid", 1.0)])
        self.assertIn("mqtt_publish_entered", hub._clock.marks)
        self.assertIn("mqtt_publish_returned", hub._clock.marks)
        self.assertIn("mqtt_response_received", hub._clock.marks)
        observed.close()
        self.assertTrue(inner.closed)

    def test_timeout_marks_error_and_propagates(self):
        hub = pilot.TimingHub()
        clock = hub.begin()
        observed = pilot.ObservedMqttClient(
            FakeClient(error=MQTTTimeoutError()), hub
        )
        with self.assertRaises(MQTTTimeoutError):
            observed.wait_for_response("topic", "cid", 0.01)
        self.assertIn("mqtt_response_error", clock.marks)
        self.assertNotIn("mqtt_response_received", clock.marks)


class AttachObserverTests(unittest.TestCase):
    def test_attaches_to_composed_mqtt_driver(self):
        runtime, mqtt_driver, _client = make_observer_runtime()
        hub = pilot.TimingHub()
        status = pilot.attach_mqtt_observer(runtime, hub)
        self.assertEqual(status, pilot.MQTT_OBSERVER_ATTACHED)
        self.assertIsInstance(mqtt_driver.client, pilot.ObservedMqttClient)

    def test_does_not_double_wrap(self):
        runtime, _mqtt_driver, _client = make_observer_runtime()
        hub = pilot.TimingHub()
        self.assertEqual(
            pilot.attach_mqtt_observer(runtime, hub),
            pilot.MQTT_OBSERVER_ATTACHED,
        )
        self.assertEqual(
            pilot.attach_mqtt_observer(runtime, hub),
            pilot.MQTT_OBSERVER_NOT_ATTACHED,
        )

    def test_not_attached_for_plain_router(self):
        harness, runtime, _router, _evidence, _bus = make_harness()
        self.assertEqual(
            pilot.attach_mqtt_observer(runtime, pilot.TimingHub()),
            pilot.MQTT_OBSERVER_NOT_ATTACHED,
        )


class LatencyRuleTests(unittest.TestCase):
    def test_timeout_never_becomes_round_trip(self):
        latencies, notes = pilot._derive_latencies(
            pilot.OUTCOME_EXECUTION_FAILED,
            0,
            10_000_000,
            20_000_000,
            30_000_000,
            40_000_000,
            50_000_000,
            {"mqtt_publish_entered": 100, "mqtt_response_error": 200},
            True,
        )
        self.assertIsNone(latencies["mqtt_round_trip_ms"])
        self.assertIsNone(latencies["end_to_end_ms"])
        self.assertEqual(latencies["confirm_call_ms"], 10.0)
        self.assertIn("mqtt_response_not_received", notes)
        self.assertIn("end_to_end_only_on_success", notes)

    def test_success_records_round_trip(self):
        latencies, notes = pilot._derive_latencies(
            pilot.OUTCOME_EXECUTED,
            0,
            10_000_000,
            20_000_000,
            30_000_000,
            40_000_000,
            50_000_000,
            {
                "mqtt_publish_entered": 100_000_000,
                "mqtt_response_received": 250_000_000,
            },
            True,
        )
        self.assertEqual(latencies["mqtt_round_trip_ms"], 150.0)
        self.assertEqual(latencies["end_to_end_ms"], 50.0)
        self.assertNotIn("end_to_end_only_on_success", notes)


class CampaignTests(unittest.TestCase):
    def test_dry_run_prepares_and_cancels(self):
        harness, _runtime, router, _evidence, bus = make_harness()
        with tempfile.TemporaryDirectory() as tmp:
            campaign, summary = run_campaign(
                harness, bus, tmp, dry_run=True, observe="ignored"
            )
            self.assertEqual(len(campaign.records), 2)
            self.assertEqual(router.calls, [])
            for record in campaign.records:
                self.assertEqual(record["outcome"], pilot.OUTCOME_DRY_RUN)
                self.assertEqual(record["prepare"]["status"], "confirmation_required")
                self.assertEqual(record["cancel_result"]["status"], "cancelled")
                self.assertFalse(record["confirmation_submitted"])
                self.assertIsNone(record["operator_observation"])
                self.assertEqual(record["runtime_invocations_delta"], 0)
                self.assertIsNotNone(record["latencies"]["decision_ms"])
                self.assertIsNotNone(record["latencies"]["prepare_ms"])
                self.assertIsNone(record["latencies"]["end_to_end_ms"])
            self.assertEqual(summary["outcomes"], {"dry_run_prepared_only": 2})
            self.assertEqual(summary["runtime_invocations_this_run"], 0)
            trials = Path(tmp) / "trials.jsonl"
            lines = [
                line
                for line in trials.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(lines), 2)
            for line in lines:
                json.loads(line)
            self.assertTrue((Path(tmp) / "summary.json").exists())
            self.assertTrue((Path(tmp) / "operator_notes.md").exists())

    def test_executed_trials_invoke_runtime_once(self):
        harness, _runtime, router, _evidence, bus = make_harness(succeed=True)
        with tempfile.TemporaryDirectory() as tmp:
            campaign, summary = run_campaign(
                harness, bus, tmp, dry_run=False, confirm=True, observe="on"
            )
            self.assertEqual(len(router.calls), 2)
            self.assertEqual(summary["outcomes"], {"executed": 2})
            self.assertEqual(summary["runtime_invocations_this_run"], 2)
            for record in campaign.records:
                self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTED)
                self.assertEqual(record["runtime_invocations_delta"], 1)
                self.assertIsNotNone(record["latencies"]["end_to_end_ms"])
                self.assertIsNone(record["latencies"]["mqtt_round_trip_ms"])
                self.assertIn("mqtt_observer_not_attached", record["timing_notes"])
                self.assertTrue(
                    any(
                        event["type"] == COMMAND_EXECUTION_STARTED_EVENT
                        for event in record["runtime_events"]
                    )
                )
            self.assertEqual(
                summary["operator_observations"],
                {"on": 2, "off": 0, "not_observed": 0, "contradicted": 0},
            )
            self.assertEqual(
                summary["operator_observation_vs_request"],
                {"match": 1, "mismatch": 1},
            )

    def test_execution_failure_keeps_success_latencies_null(self):
        harness, _runtime, router, _evidence, bus = make_harness(succeed=False)
        with tempfile.TemporaryDirectory() as tmp:
            campaign, summary = run_campaign(harness, bus, tmp, dry_run=False)
            self.assertEqual(len(router.calls), 2)
            self.assertEqual(summary["outcomes"], {"execution_failed": 2})
            for record in campaign.records:
                self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTION_FAILED)
                self.assertEqual(record["runtime_invocations_delta"], 1)
                self.assertIsNone(record["latencies"]["end_to_end_ms"])
                self.assertIsNone(record["latencies"]["mqtt_round_trip_ms"])
                self.assertIsNotNone(record["latencies"]["confirm_call_ms"])
                self.assertIn("end_to_end_only_on_success", record["timing_notes"])

    def test_declined_confirmation_never_executes(self):
        harness, _runtime, router, _evidence, bus = make_harness()
        with tempfile.TemporaryDirectory() as tmp:
            campaign, summary = run_campaign(
                harness, bus, tmp, dry_run=False, confirm=False
            )
            self.assertEqual(router.calls, [])
            self.assertEqual(summary["outcomes"], {"declined": 2})
            for record in campaign.records:
                self.assertFalse(record["confirmation_submitted"])
                self.assertEqual(record["cancel_result"]["status"], "cancelled")
                self.assertEqual(record["runtime_invocations_delta"], 0)
            self.assertEqual(summary["runtime_invocations_this_run"], 0)

    def test_outputs_written_per_trial(self):
        harness, _runtime, _router, _evidence, bus = make_harness()
        with tempfile.TemporaryDirectory() as tmp:
            campaign, _summary = run_campaign(harness, bus, tmp, dry_run=True)
            trials_path = Path(tmp) / "trials.jsonl"
            self.assertTrue(trials_path.exists())
            lines = [
                line
                for line in trials_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(lines), len(campaign.records))
            for line in lines:
                json.loads(line)
            summary = json.loads(
                (Path(tmp) / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["trials_recorded"], 2)
            self.assertTrue((Path(tmp) / "operator_notes.md").exists())


class PassiveAckObserverTests(unittest.TestCase):
    """Passive ACK diagnostics: per-trial fields and fault matrix."""

    def _run_single(
        self,
        tmp,
        *,
        response=None,
        error=None,
        requested="off",
        late_response=None,
        fault_case="nominal",
        attach=True,
    ):
        harness, _runtime, mqtt_driver, client, bus = make_fault_runtime(
            response=response, error=error
        )
        status = (
            pilot.MQTT_OBSERVER_ATTACHED
            if attach
            else pilot.MQTT_OBSERVER_NOT_ATTACHED
        )
        campaign, _summary = run_campaign(
            harness,
            bus,
            tmp,
            dry_run=False,
            specs=single_spec(requested),
            observer_status=status,
            fault_case=fault_case,
            late_response=late_response,
        )
        return campaign.records[0], mqtt_driver, client

    def test_nominal_correlated_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            record, _driver, _client = self._run_single(
                tmp, response=valid_response("req-fixed", False)
            )
        self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTED)
        self.assertTrue(record["observer_attached"])
        self.assertTrue(record["observer_request_seen"])
        self.assertTrue(record["observer_response_seen"])
        self.assertFalse(record["response_after_driver_return"])
        self.assertFalse(record["late_response"])
        self.assertTrue(record["response_schema_valid"])
        self.assertEqual(record["request_id"], "req-fixed")
        self.assertEqual(record["observed_response_request_id"], "req-fixed")
        self.assertTrue(record["request_id_match"])
        self.assertIs(record["observed_response_state"], False)
        self.assertTrue(record["semantic_state_match"])
        self.assertFalse(record["observer_saw_response_driver_failed"])
        self.assertIsNotNone(record["observer_request_seen_monotonic"])
        self.assertIsNotNone(record["observer_response_seen_monotonic"])
        self.assertIsNotNone(record["observer_response_delay_ms"])
        self.assertGreaterEqual(record["observer_response_delay_ms"], 0.0)

    def test_no_response_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            record, _driver, _client = self._run_single(
                tmp, error=MQTTTimeoutError()
            )
        self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTION_FAILED)
        self.assertEqual(record["request_id"], "req-fixed")
        self.assertTrue(record["observer_request_seen"])
        self.assertFalse(record["observer_response_seen"])
        self.assertFalse(record["response_after_driver_return"])
        self.assertFalse(record["late_response"])
        self.assertIsNone(record["response_schema_valid"])
        self.assertIsNone(record["observed_response_request_id"])
        self.assertIsNone(record["request_id_match"])
        self.assertIsNone(record["observed_response_state"])
        self.assertIsNone(record["semantic_state_match"])
        self.assertFalse(record["observer_saw_response_driver_failed"])

    def test_late_response_after_driver_return(self):
        late = valid_response("req-fixed", False)
        with tempfile.TemporaryDirectory() as tmp:
            record, _driver, _client = self._run_single(
                tmp, error=MQTTTimeoutError(), late_response=late
            )
        self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTION_FAILED)
        self.assertTrue(record["observer_request_seen"])
        self.assertTrue(record["observer_response_seen"])
        self.assertTrue(record["response_after_driver_return"])
        self.assertTrue(record["late_response"])
        self.assertTrue(record["response_schema_valid"])
        self.assertTrue(record["request_id_match"])
        self.assertIs(record["observed_response_state"], False)
        self.assertTrue(record["semantic_state_match"])
        self.assertTrue(record["observer_saw_response_driver_failed"])
        self.assertIsNotNone(record["observer_response_delay_ms"])

    def test_invalid_schema(self):
        bad = json.dumps(
            {"request_id": "req-fixed", "ok": "yes", "semantic": {}, "error": None}
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            record, _driver, _client = self._run_single(tmp, response=bad)
        self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTION_FAILED)
        self.assertTrue(record["observer_response_seen"])
        self.assertFalse(record["response_schema_valid"])
        self.assertIsNone(record["observed_response_state"])
        self.assertTrue(record["observer_saw_response_driver_failed"])

    def test_wrong_request_id(self):
        wrong = valid_response("some-other-id", False)
        with tempfile.TemporaryDirectory() as tmp:
            record, _driver, _client = self._run_single(tmp, response=wrong)
        self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTION_FAILED)
        self.assertTrue(record["response_schema_valid"])
        self.assertEqual(record["observed_response_request_id"], "some-other-id")
        self.assertFalse(record["request_id_match"])
        self.assertTrue(record["observer_saw_response_driver_failed"])

    def test_semantic_mismatch(self):
        mismatch = valid_response("req-fixed", False)
        with tempfile.TemporaryDirectory() as tmp:
            record, _driver, _client = self._run_single(
                tmp, response=mismatch, requested="on"
            )
        self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTION_FAILED)
        self.assertTrue(record["response_schema_valid"])
        self.assertTrue(record["request_id_match"])
        self.assertIs(record["observed_response_state"], False)
        self.assertFalse(record["semantic_state_match"])
        self.assertTrue(record["observer_saw_response_driver_failed"])

    def test_observer_sees_response_while_driver_fails(self):
        # A structurally valid but uncorrelated response: the observer sees a
        # response, yet the driver rejects it and reports failure.
        wrong = valid_response("uncorrelated-id", False)
        with tempfile.TemporaryDirectory() as tmp:
            record, _driver, _client = self._run_single(tmp, response=wrong)
        self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTION_FAILED)
        self.assertTrue(record["observer_response_seen"])
        self.assertTrue(record["observer_saw_response_driver_failed"])

    def test_fault_matrix_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            harness, _runtime, _driver, _client, bus = make_fault_runtime(
                response=valid_response("req-fixed", False)
            )
            campaign, _summary = run_campaign(
                harness,
                bus,
                tmp,
                dry_run=False,
                observer_status=pilot.MQTT_OBSERVER_ATTACHED,
                fault_case="late-ack",
            )
            matrix_path = Path(tmp) / pilot.FAULT_MATRIX_FILENAME
            self.assertTrue(matrix_path.exists())
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            self.assertEqual(matrix["row_count"], len(campaign.records))
            self.assertEqual(len(matrix["rows"]), len(campaign.records))
            self.assertEqual(matrix["fault_case"], "late-ack")
            self.assertEqual(tuple(matrix["columns"]), pilot.FAULT_MATRIX_FIELDS)
            for row in matrix["rows"]:
                for field in pilot.FAULT_MATRIX_FIELDS:
                    self.assertIn(field, row)
                self.assertEqual(row["fault_case"], "late-ack")
                self.assertIsNotNone(row["trial_index"])
                self.assertIsNotNone(row["software_outcome"])

    def test_backward_compatibility_with_old_captures(self):
        old_records = [
            {
                "schema_version": "1.0",
                "tool": pilot.TOOL_NAME,
                "trial_index": 1,
                "requested_state": "off",
                "outcome": "executed",
                "runtime_invocations_delta": 1,
                "confirmation_result": {"error": None},
                "state_before": {"status": "unknown", "properties": {}},
                "state_after": {"status": "known", "properties": {"state": False}},
                "latencies": {"mqtt_round_trip_ms": 12.5},
            }
        ]
        matrix = pilot.build_fault_matrix(
            old_records, experiment_id="old-capture", fault_case=None
        )
        self.assertEqual(matrix["row_count"], 1)
        row = matrix["rows"][0]
        for field in pilot.FAULT_MATRIX_FIELDS:
            self.assertIn(field, row)
        self.assertEqual(row["trial_index"], 1)
        self.assertIsNone(row["fault_case"])
        self.assertEqual(row["software_outcome"], "executed")
        self.assertEqual(row["mqtt_round_trip_ms"], 12.5)
        self.assertIsNone(row["request_id"])
        self.assertIsNone(row["response_schema_valid"])
        self.assertIsNone(row["request_id_match"])
        self.assertIsNone(row["semantic_state_match"])
        self.assertIsNone(row["observer_saw_response_driver_failed"])

        # The same builder works from an on-disk old-style trials.jsonl.
        with tempfile.TemporaryDirectory() as tmp:
            trials = Path(tmp) / pilot.TRIALS_FILENAME
            with trials.open("w", encoding="utf-8") as handle:
                for record in old_records:
                    handle.write(json.dumps(record) + "\n")
            loaded = pilot.load_trials_jsonl(trials)
            written = pilot.write_fault_matrix(tmp, loaded, experiment_id="old-capture")
            self.assertTrue(
                (Path(tmp) / pilot.FAULT_MATRIX_FILENAME).exists()
            )
            self.assertEqual(written["row_count"], 1)

    def test_observer_does_not_alter_execution_behavior(self):
        with tempfile.TemporaryDirectory() as tmp_off:
            plain_record, _d1, plain_client = self._run_single(
                tmp_off,
                response=valid_response("req-fixed", False),
                attach=False,
            )
        with tempfile.TemporaryDirectory() as tmp_on:
            observed_record, _d2, observed_client = self._run_single(
                tmp_on,
                response=valid_response("req-fixed", False),
                attach=True,
            )
        # Execution-relevant outcomes are identical with and without observer.
        self.assertEqual(plain_record["outcome"], observed_record["outcome"])
        self.assertEqual(
            plain_record["runtime_invocations_delta"],
            observed_record["runtime_invocations_delta"],
        )
        self.assertEqual(
            plain_record["confirmation_result"]["error"],
            observed_record["confirmation_result"]["error"],
        )
        self.assertEqual(len(plain_client.published), len(observed_client.published))
        self.assertEqual(len(plain_client.waited), len(observed_client.waited))
        # The observer adds evidence only.
        self.assertFalse(plain_record["observer_attached"])
        self.assertFalse(plain_record["observer_request_seen"])
        self.assertTrue(observed_record["observer_attached"])
        self.assertTrue(observed_record["observer_request_seen"])


class CustomProtocolTests(unittest.TestCase):
    def test_custom_protocol_and_labels(self):
        args = pilot._parse_args([
            "--pairs", "2", "--trial-states", "off", "on", "on", "off",
            "--trial-fault-cases", "F_BASELINE", "F_BROKER_OFF",
            "F_RECOVERY_WINDOW", "F_POST_RECOVERY",
        ])
        specs = pilot.protocol_trial_specs(args)
        self.assertEqual([s.requested_state for s in specs], ["off", "on", "on", "off"])
        self.assertEqual([s.fault_case for s in specs], [
            "F_BASELINE", "F_BROKER_OFF", "F_RECOVERY_WINDOW", "F_POST_RECOVERY"])
        harness, _, _, _, bus = make_harness()
        with tempfile.TemporaryDirectory() as tmp:
            campaign, _ = run_campaign(harness, bus, tmp, dry_run=True, specs=specs)
            self.assertEqual([r["fault_case"] for r in campaign.records],
                             [s.fault_case for s in specs])
            matrix = json.loads((Path(tmp) / "fault_matrix.json").read_text())
            self.assertEqual([r["fault_case"] for r in matrix["rows"]],
                             [s.fault_case for s in specs])

    def test_legacy_cli(self):
        args = pilot._parse_args(["--pairs", "2", "--fault-case", "legacy"])
        self.assertEqual([s.requested_state for s in pilot.protocol_trial_specs(args)],
                         ["off", "on", "off", "on"])
        harness, _, _, _, bus = make_harness()
        with tempfile.TemporaryDirectory() as tmp:
            campaign, _ = run_campaign(harness, bus, tmp, dry_run=True,
                                      fault_case=args.fault_case)
            self.assertTrue(all(r["fault_case"] == "legacy" for r in campaign.records))

    def test_invalid_protocol_before_composition_or_artifacts(self):
        cases = [
            ["--trial-states", "off"],
            ["--trial-states", "off", "--trial-fault-cases", "A"],
            ["--trial-states", "off", "on", "on", "off",
             "--trial-fault-cases", "A", "B", "C"],
            ["--trial-states", "off", "on", "invalid", "off",
             "--trial-fault-cases", "A", "B", "C", "D"],
            ["--trial-states", "off", "on", "on", "off",
             "--trial-fault-cases", "A", "B", " ", "D"],
            ["--ack-observation-window", "nan"],
            ["--ack-observation-window", "0"],
        ]
        for flags in cases:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "new"
                with patch.object(pilot, "compose_runtime") as compose:
                    self.assertEqual(pilot.main(["--pairs", "2", "--out-dir", str(out)] + flags), 2)
                    compose.assert_not_called()
                    self.assertFalse(out.exists())


class FakeSubscriberClient:
    def __init__(self):
        self.subscriptions = []
        self.stopped = False

    def connect(self, host, port, keepalive):
        self.connection = (host, port, keepalive)

    def loop_start(self):
        self.on_connect(self, None, None, 0)
        for mid in range(1, len(self.subscriptions) + 1):
            self.on_subscribe(self, None, mid, [0])

    def subscribe(self, topic, qos):
        self.subscriptions.append((topic, qos))
        return 0, len(self.subscriptions)

    def disconnect(self):
        pass

    def loop_stop(self):
        self.stopped = True

    def emit(self, topic, payload, retain=False):
        self.on_message(self, None, SimpleNamespace(topic=topic, payload=payload, retain=retain))


class IndependentAckTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeSubscriberClient()
        self.observer = pilot.PassiveAckSubscriber(
            self.client, "localhost", 1883, "request", "response")
        self.observer.start(0.01)
        self.observer.begin_trial()

    def tearDown(self):
        self.observer.close()

    def request(self):
        self.client.emit("request", b'{"request_id":"req"}')

    def fields(self, response=None, late=False, outcome=pilot.OUTCOME_EXECUTION_FAILED):
        self.request()
        if late:
            self.observer.driver_returned()
        if response is not None:
            self.client.emit("response", response)
        observation = self.observer.finish_trial(4, wait_fn=lambda seconds: None)
        return pilot.derive_observation_fields(observation, fault_case="test",
            requested_state="off", outcome=outcome, observer_attached=True)

    def test_nominal(self):
        fields = self.fields(valid_response("req", False), outcome=pilot.OUTCOME_EXECUTED)
        self.assertTrue(fields["request_id_match"])
        self.assertTrue(fields["semantic_state_match"])
        self.assertFalse(fields["late_response"])

    def test_no_response(self):
        fields = self.fields()
        self.assertFalse(fields["observer_response_seen"])
        self.assertIsNone(fields["response_schema_valid"])

    def test_real_callback_after_return(self):
        self.request()
        self.observer.driver_returned()
        waits = []
        def wait(seconds):
            waits.append(seconds)
            self.client.emit("response", valid_response("req", False))
        observation = self.observer.finish_trial(4, wait_fn=wait)
        fields = pilot.derive_observation_fields(observation, fault_case="test",
            requested_state="off", outcome=pilot.OUTCOME_EXECUTION_FAILED, observer_attached=True)
        self.assertEqual(len(waits), 1)
        self.assertGreater(waits[0], 0)
        self.assertLessEqual(waits[0], 4)
        self.assertTrue(fields["late_response"])
        self.assertTrue(fields["response_after_driver_return"])
        self.assertGreater(fields["observer_response_seen_monotonic"], observation.driver_returned_ns)
        self.assertTrue(fields["observer_saw_response_driver_failed"])

    def test_malformed_late(self):
        fields = self.fields(b"broken", late=True)
        self.assertTrue(fields["observer_response_seen"])
        self.assertTrue(fields["response_after_driver_return"])
        self.assertFalse(fields["late_response"])
        self.assertFalse(fields["response_schema_valid"])

    def test_wrong_id_late(self):
        fields = self.fields(valid_response("other", False), late=True)
        self.assertFalse(fields["request_id_match"])
        self.assertFalse(fields["late_response"])
        self.assertTrue(fields["response_after_driver_return"])

    def test_semantic_mismatch(self):
        self.assertFalse(self.fields(valid_response("req", True))["semantic_state_match"])

    def test_duplicate_and_unrelated_response_do_not_replace_match(self):
        self.request()
        self.client.emit("response", b"bad")
        self.client.emit("response", valid_response("req", False))
        self.client.emit("response", valid_response("other", True))
        fields = self.fields()
        self.assertTrue(fields["request_id_match"])
        self.assertTrue(fields["semantic_state_match"])

    def test_only_relevant_nonretained_traffic(self):
        self.client.emit("request", b'{"request_id":"old"}', retain=True)
        self.client.emit("other", valid_response("req", False))
        observation = self.observer.finish_trial(4, wait_fn=lambda seconds: None)
        self.assertFalse(observation.request_seen)
        self.assertFalse(observation.response_seen)
        self.assertEqual(self.client.subscriptions, [("request", 0), ("response", 0)])
        self.assertFalse(hasattr(self.observer, "publish"))

    def test_subscription_readiness_failure(self):
        client = FakeSubscriberClient()
        client.loop_start = lambda: None
        observer = pilot.PassiveAckSubscriber(client, "localhost", 1883, "request", "response")
        with self.assertRaisesRegex(RuntimeError, "passive_observer_not_ready"):
            observer.start(0.001)
        observer.close()

    def test_reconnect_resubscribes_before_ready(self):
        self.observer._on_disconnect()
        self.assertFalse(self.observer._ready.is_set())
        self.observer._on_connect(self.client, None, None, 0)
        self.assertFalse(self.observer._ready.is_set())
        self.observer._on_subscribe(self.client, None, 3, [0])
        self.assertFalse(self.observer._ready.is_set())
        self.observer._on_subscribe(self.client, None, 4, [0])
        self.assertTrue(self.observer._ready.is_set())

    def test_oversized_response_preserves_receipt_without_payload(self):
        self.observer.max_response_bytes = 32
        fields = self.fields(b"x" * 33, late=True)
        self.assertTrue(fields["observer_response_seen"])
        self.assertFalse(fields["response_schema_valid"])
        self.assertFalse(fields["late_response"])

    def test_subscription_denial_never_ready(self):
        self.observer._on_connect(self.client, None, None, 0)
        self.observer._on_subscribe(self.client, None, 3, [128])
        self.observer._on_subscribe(self.client, None, 4, [0])
        self.assertFalse(self.observer._ready.is_set())

    def test_response_outside_window_is_not_observed(self):
        self.request()
        with patch.object(pilot, "_now_ns", return_value=100):
            self.observer.driver_returned()
        with patch.object(pilot, "_now_ns", return_value=4_000_000_101):
            self.client.emit("response", valid_response("req", False))
        self.assertFalse(self.observer._observation.response_seen)

    def test_finished_trial_does_not_capture_next_response(self):
        self.request()
        self.observer.finish_trial(4, wait_fn=lambda _: None)
        self.client.emit("response", valid_response("req", False))
        self.observer.begin_trial()
        self.assertFalse(self.observer._observation.response_seen)

    def test_manifest_window_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "manifest.json"
            with patch.object(pilot.manifest_tool, "build_manifest", return_value={}):
                pilot.build_manifest("test", "label", None, Path("profile"), out,
                                     ack_observation_window_seconds=3)
            self.assertEqual(json.loads(out.read_text())["ack_observation_window_seconds"], 3)

    def test_boundary_preserves_result_and_exception(self):
        inner = FakeRouter()
        sentinel = object()
        inner.apply = lambda *args: sentinel
        boundary = pilot.ObservedDriverBoundary(inner, self.observer)
        self.assertIs(boundary.apply(None, None, {}), sentinel)
        self.assertIsNotNone(self.observer._observation.driver_returned_ns)
        def fail(*args):
            raise MQTTTimeoutError()
        inner.apply = fail
        with self.assertRaises(MQTTTimeoutError):
            boundary.apply(None, None, {})

    def test_independent_response_cannot_change_failed_execution(self):
        harness, runtime, driver, command_client, bus = make_fault_runtime(error=MQTTTimeoutError())
        runtime.context.capability_registry.resolve(pilot.DEVICE_EXECUTE_COMMAND).router.driver._drivers[DEVICE_ID] = (
            pilot.ObservedDriverBoundary(driver, self.observer))
        original_publish = command_client.publish
        def publish(topic, payload):
            original_publish(topic, payload)
            self.client.emit("request", payload)
        command_client.publish = publish
        original_finish = self.observer.finish_trial
        def finish(seconds):
            return original_finish(seconds, wait_fn=lambda _: self.client.emit(
                "response", valid_response("req-fixed", False)))
        self.observer.finish_trial = finish
        with tempfile.TemporaryDirectory() as tmp:
            campaign = pilot.PilotCampaign(harness=harness, hub=pilot.TimingHub(),
                out_dir=Path(tmp), specs=single_spec("off"), dry_run=False,
                confirm_fn=lambda: True, observe_fn=lambda: "off", verbose=False,
                mqtt_observer_status=pilot.MQTT_OBSERVER_ATTACHED,
                passive_subscriber=self.observer)
            campaign.run()
            record = campaign.records[0]
        self.assertEqual(record["outcome"], pilot.OUTCOME_EXECUTION_FAILED)
        self.assertEqual(record["runtime_invocations_delta"], 1)
        self.assertEqual(len(command_client.published), 1)
        self.assertTrue(record["late_response"])
        self.assertTrue(record["observer_saw_response_driver_failed"])
        self.assertEqual(record["ack_observation_window_seconds"], 4)
        self.assertIsNone(record["latencies"]["mqtt_round_trip_ms"])


class PassiveSubscriberStartupTests(unittest.TestCase):
    def test_unavailable_client_degrades_without_attribute_error(self):
        runtime, driver = make_broker_runtime(UnavailableMQTTClient())
        hub = pilot.TimingHub()
        self.assertEqual(
            pilot.attach_mqtt_observer(runtime, hub), pilot.MQTT_OBSERVER_ATTACHED
        )
        # No broker is configured, so the independent subscriber must report
        # itself unavailable instead of raising AttributeError on the missing
        # broker-coordinate attributes of UnavailableMQTTClient.
        self.assertIsNone(pilot.broker_capable_client(driver))
        self.assertIsNone(pilot.start_passive_ack_subscriber(runtime, 0.01))
        self.assertIs(
            runtime.context.capability_registry.resolve(
                pilot.DEVICE_EXECUTE_COMMAND
            ).router.driver._drivers[DEVICE_ID],
            driver,
        )

    def test_starts_against_real_paho_client(self):
        runtime, _driver = make_broker_runtime(PahoMQTTClient(host="127.0.0.1"))
        fake = FakeSubscriberClient()
        with patch.object(paho_mqtt, "Client", return_value=fake) as factory:
            subscriber = pilot.start_passive_ack_subscriber(runtime, 0.01)
            self.assertIsInstance(subscriber, pilot.PassiveAckSubscriber)
            self.assertEqual(
                factory.call_args.kwargs.get("callback_api_version"),
                paho_mqtt.CallbackAPIVersion.VERSION2,
            )
        self.assertIsNotNone(subscriber)
        self.assertEqual(
            fake.subscriptions,
            [("jarvis/request", 0), ("jarvis/response", 0)],
        )
        drivers = (
            runtime.context.capability_registry.resolve(pilot.DEVICE_EXECUTE_COMMAND)
            .router.driver._drivers
        )
        self.assertIsInstance(drivers[DEVICE_ID], pilot.ObservedDriverBoundary)
        subscriber.close()


if __name__ == "__main__":
    unittest.main()
