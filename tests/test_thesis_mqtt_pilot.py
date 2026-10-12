"""Tests for the thesis-only guarded MQTT pilot tool.

These tests use real JarvisOS resolver, ExecutionGate, Runtime,
DeviceRuntimeCapability and EventBus, with fake routers and fake MQTT clients.
They never touch the network, a broker, MQTT deployment configuration, the
State Store, firmware or hardware.
"""

from __future__ import annotations

import json
import tempfile
import unittest
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
)
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


if __name__ == "__main__":
    unittest.main()