"""Thesis-only quantitative pilot for the guarded ESP32 MQTT vertical.

This tool runs a deterministic sequence of guarded ON/OFF trials through the
existing, unmodified execution path:

    SafeContextBuilder
    -> decide_understanding
    -> DeterministicUnderstandingResolver
    -> LocalUnderstandingDecision
    -> ExecutionGate.prepare
    -> explicit human confirmation (typed in this same process)
    -> ExecutionGate.confirm
    -> Runtime
    -> DeviceRuntimeCapability
    -> DeviceCommandRouter
    -> MQTTDeviceDriver
    -> PahoMQTTClient
    -> NanoMQ
    -> ESP32 relay_1

It captures one structured record per initiated trial under
``captures/thesis/<experiment_id>/`` so a thesis can cite host-measured
timings and operator observations.

Design boundaries (additive evidence tooling; changes no core behavior):

- No core module, profile, driver, transport, firmware or Runtime behavior is
  modified. ``ExecutionGate``, the confirmation store, ``Runtime``, the
  router, the MQTT driver and the bootstrap composition are used as-is.
- No parallel execution or MQTT path is introduced. The Runtime is composed
  once through the existing guarded harness; every mutation still requires an
  explicit human ``CONFIRM`` typed in this same running process. There is no
  ``--confirm`` flag, no auto-confirm, no retry and no timeout-confirm.
- Timing uses a single host monotonic clock (``time.monotonic_ns``). ESP32
  timestamps are never read, subtracted or fabricated. A transport timeout is
  never recorded as a successful latency: success-gated latencies stay ``null``
  when the corresponding success did not occur, and the reason is recorded in
  ``timing_notes``.
- The optional MQTT observer is passive: it wraps the already-composed
  ``MQTTDeviceDriver.client`` in a delegating object that only records the
  local monotonic instants at which ``publish`` and ``wait_for_response`` are
  entered and return. It never alters payloads, topics, timeouts or results,
  never reorders execution and never retries. It degrades gracefully to
  ``null`` timings when the seam is unavailable. Use ``--no-mqtt-observer`` to
  disable it entirely.
- A separate receive-only Paho subscriber observes the exact request/response
  topics before confirmation and for a bounded post-driver window. Its data
  cannot satisfy the driver's wait or change execution outcomes. Retained
  traffic is excluded; absent traffic means not observed, never not emitted.
- Operator observation is a human judgment recorded separately. Software
  semantic state never proves physical state; the records say so explicitly.
- Outputs land under the gitignored ``captures/`` tree. No commit, push,
  hardware or network interaction happens in tests.

Usage:

    python tools/run_thesis_mqtt_pilot.py --pairs 10
    python tools/run_thesis_mqtt_pilot.py --dry-run --pairs 2
    python tools/run_thesis_mqtt_pilot.py --experiment-id my-run --pairs 10

``--dry-run`` runs understanding + ``prepare`` + ``cancel`` only. It never
confirms and therefore never touches the network, even when a broker is
configured, because the Paho client connects lazily on first publish.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import statistics
import sys
import time
import threading
from uuid import uuid4
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for _path in (str(REPO_ROOT), str(TOOLS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import capture_thesis_experiment_manifest as manifest_tool  # noqa: E402
import run_guarded_hardware_validation as guarded  # noqa: E402

from jarvis_core.ai.execution_gate import (  # noqa: E402
    GATE_STATUS_CONFIRMATION_REQUIRED,
    GATE_STATUS_EXECUTED,
)
from jarvis_core.ai.understanding_decision import EXECUTABLE_CANDIDATE  # noqa: E402
from jarvis_core.mqtt_driver import MQTTDeviceDriver  # noqa: E402
from jarvis_core.planner import DEVICE_EXECUTE_COMMAND  # noqa: E402
from jarvis_core.runtime import (  # noqa: E402
    CAPABILITY_EXECUTION_COMPLETED_EVENT,
    CAPABILITY_EXECUTION_FAILED_EVENT,
    COMMAND_EXECUTION_STARTED_EVENT,
)


SCHEMA_VERSION = "1.0"
TOOL_NAME = "run_thesis_mqtt_pilot.py"
LATENCY_BASIS = "host_monotonic_only"

DEFAULT_EXPERIMENT_ID = "guarded_mqtt_pilot"
DEFAULT_PAIRS = 10
DEFAULT_OUTPUT_ROOT = "captures/thesis"

OBSERVATIONS = ("on", "off", "not_observed", "contradicted")

REQUESTED_OFF = "off"
REQUESTED_ON = "on"

OUTCOME_EXECUTED = "executed"
OUTCOME_EXECUTION_FAILED = "execution_failed"
OUTCOME_DECLINED = "declined"
OUTCOME_REFUSED = "refused_before_prepare"
OUTCOME_DECISION_UNAVAILABLE = "decision_unavailable"
OUTCOME_PREPARE_FAILED = "prepare_failed"
OUTCOME_DRY_RUN = "dry_run_prepared_only"

SUCCESS_OUTCOMES = frozenset({OUTCOME_EXECUTED, OUTCOME_DRY_RUN})

MQTT_OBSERVER_ATTACHED = "attached"
MQTT_OBSERVER_NOT_ATTACHED = "not_attached"

LATENCY_KEYS = (
    "decision_ms",
    "prepare_ms",
    "confirm_call_ms",
    "end_to_end_ms",
    "mqtt_round_trip_ms",
)

DISCLAIMER = (
    "Software semantic state never proves physical device state. Physical "
    "state is a separate operator observation. Timing values are host "
    "monotonic durations only; a transport timeout is never recorded as a "
    "successful latency."
)

FIRMWARE_SOURCES = (
    "examples/esp32-mqtt-relay/CMakeLists.txt",
    "examples/esp32-mqtt-relay/main/CMakeLists.txt",
    "examples/esp32-mqtt-relay/main/esp32-mqtt-relay.c",
    "examples/esp32-mqtt-relay/main/mqtt_broker.h",
    "examples/esp32-mqtt-relay/main/mqtt_broker.example.h",
    "examples/esp32-mqtt-relay/main/wifi_credentials.h",
    "examples/esp32-mqtt-relay/main/wifi_credentials.example.h",
    "examples/esp32-mqtt-relay/sdkconfig",
)


# -- passive ACK diagnostic constants ----------------------------------------

TRIALS_FILENAME = "trials.jsonl"
FAULT_MATRIX_FILENAME = "fault_matrix.json"
FAULT_MATRIX_SCHEMA_VERSION = "1.0"
DEFAULT_FAULT_CASE = "nominal"
DEFAULT_ACK_WINDOW_SECONDS = 4.0

OBSERVED_RESPONSE_FIELDS = frozenset({"request_id", "ok", "semantic", "error"})
POWER_SWITCH_STATE_KEY = "state"

FAULT_MATRIX_FIELDS = (
    "trial_index",
    "fault_case",
    "requested_state",
    "software_outcome",
    "software_error",
    "runtime_invocations_delta",
    "request_id",
    "observer_request_seen",
    "observer_response_seen",
    "response_after_driver_return",
    "late_response",
    "response_schema_valid",
    "request_id_match",
    "semantic_state_match",
    "observer_saw_response_driver_failed",
    "operator_observation",
    "mqtt_round_trip_ms",
    "semantic_state_before",
    "semantic_state_after",
)

PER_TRIAL_OBSERVATION_FIELDS = (
    "fault_case",
    "request_id",
    "observer_attached",
    "observer_request_seen",
    "observer_response_seen",
    "observer_request_seen_monotonic",
    "observer_response_seen_monotonic",
    "observer_response_delay_ms",
    "response_after_driver_return",
    "late_response",
    "response_schema_valid",
    "observed_response_request_id",
    "request_id_match",
    "observed_response_state",
    "semantic_state_match",
    "observer_saw_response_driver_failed",
)


def _decode_observed_payload(payload):
    """Read an observed request/response payload without mutating it."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except Exception:
            return None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    return payload


def observed_request_id(payload):
    """Return the request_id present in an observed request envelope, else None."""
    envelope = _decode_observed_payload(payload)
    if envelope is None:
        return None
    request_id = envelope.get("request_id")
    if isinstance(request_id, str) and request_id:
        return request_id
    return None


def observed_response_summary(response):
    """Passively read an observed response envelope. Never mutates anything.

    Returns ``None`` when no response was observed, otherwise a dict with
    ``schema_valid`` (matching the driver's accepted envelope), the observed
    ``request_id`` and the observed power-switch ``state`` (bool or None).
    """
    if response is None:
        return None
    envelope = _decode_observed_payload(response)
    valid = False
    request_id = None
    state = None
    if envelope is not None:
        request_id = envelope.get("request_id")
        ok = envelope.get("ok")
        semantic = envelope.get("semantic")
        error = envelope.get("error")
        valid = (
            set(envelope.keys()) == OBSERVED_RESPONSE_FIELDS
            and isinstance(request_id, str)
            and bool(request_id)
            and isinstance(ok, bool)
            and isinstance(semantic, dict)
            and (error is None or (isinstance(error, str) and bool(error)))
        )
        if isinstance(semantic, dict):
            candidate = semantic.get(POWER_SWITCH_STATE_KEY)
            if type(candidate) is bool:
                state = candidate
    return {"schema_valid": valid, "request_id": request_id, "state": state}


class TrialObservation:
    """Per-trial passive observation of one MQTT request/response exchange.

    This object only records facts. It never publishes, acknowledges, mutates
    driver state or changes an execution outcome. All timing is host monotonic.
    """

    def __init__(self, attached=False):
        self.attached = bool(attached)
        self.request_seen = False
        self.request_seen_ns = None
        self.request_id = None
        self.response_seen = False
        self.response_seen_ns = None
        self.response = None
        self.response_in_band = False
        self.timeout_seen = False
        self.driver_returned_ns = None
        self.late_response_seen = False
        self.late_response_ns = None
        self.late_response = None

    def mark_request(self, request_id, seen_ns):
        if self.request_seen:
            return
        self.request_seen = True
        self.request_seen_ns = seen_ns
        self.request_id = request_id

    def mark_response(self, response, seen_ns, in_band=True):
        if self.response_seen:
            return
        self.response_seen = True
        self.response_seen_ns = seen_ns
        self.response = response
        self.response_in_band = in_band

    def mark_timeout(self):
        self.timeout_seen = True

    def mark_driver_returned(self, seen_ns):
        self.driver_returned_ns = seen_ns

    def mark_late_response(self, response, seen_ns):
        if self.driver_returned_ns is None:
            self.mark_response(response, seen_ns, in_band=False)
            return
        self.late_response_seen = True
        self.late_response_ns = seen_ns
        self.late_response = response


def derive_observation_fields(
    observation,
    *,
    fault_case,
    requested_state,
    outcome,
    observer_attached,
):
    """Derive the per-trial passive observation fields from raw observations.

    Pure function of recorded facts. When evidence is absent it records
    ``None``/``False`` and never infers a physical state or a root cause.
    """
    if observation is None:
        observation = TrialObservation()

    response = observation.response if observation.response_seen else None
    if response is None and observation.late_response_seen:
        response = observation.late_response
    summary = observed_response_summary(response) if response is not None else None

    schema_valid = summary["schema_valid"] if summary is not None else None
    observed_request_id = summary["request_id"] if summary is not None else None
    observed_state = summary["state"] if summary is not None else None

    request_id_match = None
    if observed_request_id is not None and observation.request_id is not None:
        request_id_match = observed_request_id == observation.request_id

    semantic_state_match = None
    if observed_state is not None:
        semantic_state_match = observed_state == (requested_state == REQUESTED_ON)

    response_seen = bool(observation.response_seen or observation.late_response_seen)
    late_response = bool(observation.late_response_seen and request_id_match is True)
    response_ns = observation.response_seen_ns
    if response_ns is None:
        response_ns = observation.late_response_ns

    return {
        "fault_case": fault_case,
        "request_id": observation.request_id,
        "observer_attached": bool(observer_attached),
        "observer_request_seen": bool(observation.request_seen),
        "observer_response_seen": response_seen,
        "observer_request_seen_monotonic": observation.request_seen_ns,
        "observer_response_seen_monotonic": response_ns,
        "observer_response_delay_ms": _ms(observation.request_seen_ns, response_ns),
        "response_after_driver_return": bool(observation.late_response_seen),
        "late_response": late_response,
        "response_schema_valid": schema_valid,
        "observed_response_request_id": observed_request_id,
        "request_id_match": request_id_match,
        "observed_response_state": observed_state,
        "semantic_state_match": semantic_state_match,
        "observer_saw_response_driver_failed": bool(
            response_seen and outcome not in SUCCESS_OUTCOMES
        ),
    }


# -- timing ------------------------------------------------------------------


def _now_ns() -> int:
    return time.monotonic_ns()


def _ms(start_ns: Optional[int], end_ns: Optional[int]) -> Optional[float]:
    if start_ns is None or end_ns is None:
        return None
    return round((end_ns - start_ns) / 1_000_000.0, 3)


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


class TrialClock:
    """First-wins monotonic marks and bounded event facts for one trial."""

    def __init__(self) -> None:
        self.marks: dict = {}
        self.events: list = []

    def mark(self, key: str) -> None:
        self.marks.setdefault(key, _now_ns())


class TimingHub:
    """Single active trial clock and passive observation, marked by harness/observer."""

    def __init__(self) -> None:
        self._clock: Optional[TrialClock] = None
        self._observation: Optional[TrialObservation] = None
        self.observer = None
        self.attached = False

    def begin(self) -> TrialClock:
        clock = TrialClock()
        self._clock = clock
        self._observation = TrialObservation(attached=self.attached)
        return clock

    def finish_trial(self) -> None:
        self._clock = None
        self._observation = None

    @property
    def observation(self) -> Optional[TrialObservation]:
        return self._observation

    def mark(self, key: str) -> None:
        clock = self._clock
        if clock is not None:
            clock.mark(key)

    def record_event(self, entry: dict) -> None:
        clock = self._clock
        if clock is None:
            return
        try:
            clock.events.append(entry)
        except Exception:
            return

    def mark_driver_returned(self) -> Optional[int]:
        observation = self._observation
        if observation is None:
            return None
        seen_ns = _now_ns()
        observation.mark_driver_returned(seen_ns)
        return seen_ns

    def observe_request(self, request_id, seen_ns: Optional[int] = None) -> None:
        observation = self._observation
        if observation is None:
            return
        observation.mark_request(
            request_id, _now_ns() if seen_ns is None else seen_ns
        )

    def observe_response(
        self, response, seen_ns: Optional[int] = None, in_band: bool = True
    ) -> None:
        observation = self._observation
        if observation is None:
            return
        observation.mark_response(
            response, _now_ns() if seen_ns is None else seen_ns, in_band=in_band
        )

    def observe_timeout(self) -> None:
        observation = self._observation
        if observation is not None:
            observation.mark_timeout()

    def observe_late_response(
        self, response, seen_ns: Optional[int] = None
    ) -> None:
        observation = self._observation
        if observation is None:
            return
        observation.mark_late_response(
            response, _now_ns() if seen_ns is None else seen_ns
        )


class EventTimer:
    """Passive EventBus handler marking runtime entry and capability finish.

    ``EventBus.publish`` calls handlers directly without swallowing
    exceptions, so this handler must never raise.
    """

    def __init__(self, hub: TimingHub):
        self._hub = hub

    def __call__(self, event):
        try:
            event_type = getattr(event, "type", "")
            if event_type == COMMAND_EXECUTION_STARTED_EVENT:
                self._hub.mark("runtime_entered")
            elif event_type in (
                CAPABILITY_EXECUTION_COMPLETED_EVENT,
                CAPABILITY_EXECUTION_FAILED_EVENT,
            ):
                self._hub.mark("capability_finished")
            payload = getattr(event, "payload", {})
            safe = {}
            if isinstance(payload, dict):
                for key in ("command", "capability", "success", "error"):
                    if key in payload:
                        safe[key] = payload[key]
            self._hub.record_event({"type": event_type, "payload": safe})
        except Exception:
            return None


class ObservedMqttClient:
    """Passive delegating wrapper that records MQTT call instants only.

    It forwards every call unchanged and re-raises every exception unchanged.
    It does not mutate payloads, topics or timeouts and never retries.
    """

    def __init__(self, inner, hub: TimingHub):
        self._inner = inner
        self._hub = hub

    def publish(self, topic, payload):
        self._hub.mark("mqtt_publish_entered")
        self._hub.observe_request(observed_request_id(payload))
        try:
            return self._inner.publish(topic, payload)
        finally:
            self._hub.mark("mqtt_publish_returned")

    def wait_for_response(self, topic, correlation_id, timeout_seconds):
        self._hub.mark("mqtt_response_wait_entered")
        observation = self._hub.observation
        if observation is not None and not observation.request_seen:
            self._hub.observe_request(correlation_id)
        try:
            response = self._inner.wait_for_response(
                topic, correlation_id, timeout_seconds
            )
        except Exception:
            self._hub.mark("mqtt_response_error")
            self._hub.observe_timeout()
            raise
        self._hub.mark("mqtt_response_received")
        self._hub.observe_response(response)
        return response

    def observe_late_response(self, response, seen_ns=None):
        """Passively record an out-of-band response observed after the wait.

        Recording a late response never acknowledges, publishes or otherwise
        alters the underlying exchange.
        """
        try:
            self._hub.observe_late_response(response, seen_ns)
        except Exception:
            return None

    def close(self):
        return self._inner.close()


def attach_mqtt_observer(runtime, hub: TimingHub) -> str:
    """Wrap the composed MQTT client in a passive observer. Never raises.

    Returns ``MQTT_OBSERVER_ATTACHED`` or ``MQTT_OBSERVER_NOT_ATTACHED``. The
    traversal uses public attributes until the documented private
    ``DeviceTransportDriver._drivers`` lookup, which is defensive.
    """
    try:
        capability = runtime.context.capability_registry.resolve(
            DEVICE_EXECUTE_COMMAND
        )
        router = getattr(capability, "router", None)
        driver = getattr(router, "driver", None)
        drivers = getattr(driver, "_drivers", None)
        if not isinstance(drivers, dict):
            return MQTT_OBSERVER_NOT_ATTACHED
        mqtt_driver = drivers.get(guarded.DEVICE_ID)
        if not isinstance(mqtt_driver, MQTTDeviceDriver):
            return MQTT_OBSERVER_NOT_ATTACHED
        client = getattr(mqtt_driver, "client", None)
        if client is None or isinstance(client, ObservedMqttClient):
            return MQTT_OBSERVER_NOT_ATTACHED
        observer = ObservedMqttClient(client, hub)
        mqtt_driver.client = observer
        hub.observer = observer
        hub.attached = True
        return MQTT_OBSERVER_ATTACHED
    except Exception:
        return MQTT_OBSERVER_NOT_ATTACHED


# -- record helpers ----------------------------------------------------------


class PassiveAckSubscriber:
    """Independent, receive-only thesis subscriber. No driver response injection.

    Only the first response is retained, unless a later correlated response
    replaces an uncorrelated/malformed one. Retained traffic is excluded.
    """

    def __init__(self, client, host, port, request_topic, response_topic,
                 max_response_bytes=65536,
                 window_seconds=DEFAULT_ACK_WINDOW_SECONDS):
        self.client = client
        self.host, self.port = host, port
        self.request_topic, self.response_topic = request_topic, response_topic
        self.max_response_bytes = max_response_bytes
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._pending_subscriptions = set()
        self._observation = None
        client.on_connect = self._on_connect
        client.on_subscribe = self._on_subscribe
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

    def start(self, timeout_seconds):
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()
        if not self._ready.wait(timeout_seconds):
            raise RuntimeError("passive_observer_not_ready")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self._ready.clear()
        if reason_code != 0:
            return
        # Paho invokes SUBACK on the same network thread after this callback.
        self._pending_subscriptions.clear()
        for topic in (self.request_topic, self.response_topic):
            rc, mid = client.subscribe(topic, qos=0)
            if rc != 0:
                return
            self._pending_subscriptions.add(mid)

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        if any(getattr(code, "is_failure", False) or
               (isinstance(code, int) and code >= 128) for code in reason_codes):
            return
        self._pending_subscriptions.discard(mid)
        if not self._pending_subscriptions:
            self._ready.set()

    def _on_disconnect(self, *args):
        self._ready.clear()

    def begin_trial(self):
        with self._lock:
            self._observation = TrialObservation(attached=True)

    def driver_returned(self):
        with self._lock:
            if self._observation is not None:
                self._observation.mark_driver_returned(_now_ns())

    def _on_message(self, client, userdata, message):
        seen_ns = _now_ns()
        payload = getattr(message, "payload", None)
        if getattr(message, "retain", False) or not isinstance(payload, bytes):
            return
        if len(payload) > self.max_response_bytes:
            # Preserve receipt evidence without retaining unbounded data.
            if message.topic != self.response_topic:
                return
            payload = b""
        with self._lock:
            observation = self._observation
            if observation is None:
                return
            if (observation.driver_returned_ns is not None
                    and seen_ns > observation.driver_returned_ns + self.window_seconds * 1e9):
                return
            if message.topic == self.request_topic:
                request_id = observed_request_id(payload)
                if request_id:
                    observation.mark_request(request_id, seen_ns)
            elif message.topic == self.response_topic and observation.request_seen:
                old = observed_response_summary(observation.response)
                new = observed_response_summary(payload)
                if observation.response_seen and (
                    old["request_id"] == observation.request_id
                    or new["request_id"] != observation.request_id
                ):
                    return
                observation.response_seen = True
                observation.response = payload
                observation.response_seen_ns = seen_ns
                observation.late_response_seen = (
                    observation.driver_returned_ns is not None
                    and seen_ns > observation.driver_returned_ns
                )

    def finish_trial(self, window_seconds, wait_fn=None):
        with self._lock:
            returned_ns = (self._observation.driver_returned_ns
                           if self._observation is not None else None)
        remaining = window_seconds
        if returned_ns is not None:
            remaining = max(0.0, window_seconds - (_now_ns() - returned_ns) / 1e9)
        (wait_fn or threading.Event().wait)(remaining)
        with self._lock:
            observation = self._observation
            self._observation = None
            return observation

    def close(self):
        try:
            self.client.disconnect()
        except Exception:
            pass
        try:
            self.client.loop_stop()
        except Exception:
            pass


class ObservedDriverBoundary:
    """Delegate unchanged; mark actual driver return, before state coordination."""

    def __init__(self, inner, subscriber):
        self.inner, self.subscriber = inner, subscriber

    def read(self, *args):
        try:
            return self.inner.read(*args)
        finally:
            self.subscriber.driver_returned()

    def apply(self, *args):
        try:
            return self.inner.apply(*args)
        finally:
            self.subscriber.driver_returned()

    def close(self):
        return self.inner.close()


def start_passive_ack_subscriber(runtime, window_seconds=DEFAULT_ACK_WINDOW_SECONDS):
    """Use the composed broker/binding; create a distinct diagnostic client."""
    import paho.mqtt.client as mqtt

    capability = runtime.context.capability_registry.resolve(DEVICE_EXECUTE_COMMAND)
    drivers = capability.router.driver._drivers
    driver = drivers[guarded.DEVICE_ID]
    binding = driver.binding_store.get(guarded.DEVICE_ID)
    inner = driver.client
    if isinstance(inner, ObservedMqttClient):
        inner = inner._inner
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                         client_id="jarvis-thesis-observer-" + uuid4().hex)
    subscriber = PassiveAckSubscriber(
        client, inner.host, inner.port, binding.request_topic, binding.response_topic,
        max_response_bytes=inner.max_response_bytes,
        window_seconds=window_seconds,
    )
    try:
        subscriber.start(inner.connect_timeout_seconds)
    except Exception:
        subscriber.close()
        raise
    drivers[guarded.DEVICE_ID] = ObservedDriverBoundary(driver, subscriber)
    return subscriber


def _decision_summary(decision) -> dict:
    if decision is None:
        return {"status": None}
    plan = getattr(decision, "plan", None)
    return {
        "status": getattr(decision, "status", None),
        "safe_summary": getattr(plan, "safe_summary", None) if plan else None,
        "confirmation_required": getattr(decision, "confirmation_required", None),
        "provider_latency_ms": getattr(decision, "latency_ms", None),
        "failure_stage": getattr(decision, "failure_stage", None),
        "failure_category": getattr(decision, "failure_category", None),
    }


def _gate_summary(result) -> Optional[dict]:
    if result is None:
        return None
    return {
        "status": getattr(result, "status", None),
        "success": getattr(result, "success", None),
        "commands_executed": getattr(result, "commands_executed", None),
        "device_id": getattr(result, "device_id", None),
        "capability": getattr(result, "capability", None),
        "arguments": getattr(result, "arguments", None),
        "confirmation_id": getattr(result, "confirmation_id", None),
        "plan_digest": getattr(result, "plan_digest", None),
        "error": getattr(result, "error", None),
        "reason": getattr(result, "reason", None),
    }


def _derive_latencies(
    outcome,
    t0,
    t_decision,
    t_prep_in,
    t_prep_out,
    t_confirm_in,
    t_confirm_out,
    marks,
    observer_attached,
) -> tuple:
    """Return (latencies dict, timing_notes list).

    Only success-gated values are populated on success; every omitted value
    carries an explanatory note. Nothing is inferred from a timeout.
    """
    executed_ok = outcome == OUTCOME_EXECUTED
    notes = []

    publish_entered = marks.get("mqtt_publish_entered")
    response_received = marks.get("mqtt_response_received")
    response_error = marks.get("mqtt_response_error")

    mqtt_round_trip = None
    if response_received is not None:
        mqtt_round_trip = _ms(publish_entered, response_received)
    elif not observer_attached:
        notes.append("mqtt_observer_not_attached")
    elif response_error is not None:
        notes.append("mqtt_response_not_received")
    else:
        notes.append("mqtt_response_not_observed")

    latencies = {
        "decision_ms": _ms(t0, t_decision),
        "prepare_ms": _ms(t_prep_in, t_prep_out),
        "confirm_call_ms": _ms(t_confirm_in, t_confirm_out),
        "end_to_end_ms": _ms(t0, t_confirm_out) if executed_ok else None,
        "mqtt_round_trip_ms": mqtt_round_trip,
    }

    if latencies["decision_ms"] is None:
        notes.append("decision_timing_unavailable")
    if latencies["prepare_ms"] is None:
        notes.append("prepare_not_reached")
    if latencies["confirm_call_ms"] is None:
        notes.append("confirm_not_reached")
    if latencies["end_to_end_ms"] is None:
        notes.append("end_to_end_only_on_success")

    return latencies, notes


def _latency_stats(records, key) -> dict:
    values = [record.get("latencies", {}).get(key) for record in records]
    present = [value for value in values if value is not None]
    stats = {
        "count": len(present),
        "null_count": len(values) - len(present),
    }
    if present:
        stats["min_ms"] = round(min(present), 3)
        stats["median_ms"] = round(statistics.median(present), 3)
        stats["max_ms"] = round(max(present), 3)
    return stats


def append_jsonl(path: Path, record: dict) -> None:
    """Append one JSON object and fsync, preserving finished trials on crash."""
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_json_atomic(path: Path, payload: dict) -> None:
    manifest_tool.write_manifest_atomic(payload, path)


def _sha256_file(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


# -- fault matrix ------------------------------------------------------------


def _software_error(record: dict) -> Optional[str]:
    confirmation = record.get("confirmation_result") or {}
    if confirmation.get("error"):
        return confirmation.get("error")
    prepare = record.get("prepare") or {}
    if record.get("outcome") == OUTCOME_PREPARE_FAILED and prepare.get("error"):
        return prepare.get("error")
    if record.get("outcome") == OUTCOME_REFUSED:
        decision = record.get("decision") or {}
        return decision.get("failure_category") or decision.get("status")
    return None


def fault_matrix_row(record: dict) -> dict:
    """Project one trial record onto the fixed fault-matrix columns.

    Missing fields (for example in older captures) become ``None``. Nothing is
    inferred: an absent observation stays absent.
    """
    latencies = record.get("latencies") or {}
    return {
        "trial_index": record.get("trial_index"),
        "fault_case": record.get("fault_case"),
        "requested_state": record.get("requested_state"),
        "software_outcome": record.get("outcome"),
        "software_error": _software_error(record),
        "runtime_invocations_delta": record.get("runtime_invocations_delta"),
        "request_id": record.get("request_id"),
        "observer_request_seen": record.get("observer_request_seen"),
        "observer_response_seen": record.get("observer_response_seen"),
        "response_after_driver_return": record.get("response_after_driver_return"),
        "late_response": record.get("late_response"),
        "response_schema_valid": record.get("response_schema_valid"),
        "request_id_match": record.get("request_id_match"),
        "semantic_state_match": record.get("semantic_state_match"),
        "observer_saw_response_driver_failed": record.get(
            "observer_saw_response_driver_failed"
        ),
        "operator_observation": record.get("operator_observation"),
        "mqtt_round_trip_ms": latencies.get("mqtt_round_trip_ms"),
        "semantic_state_before": record.get("state_before"),
        "semantic_state_after": record.get("state_after"),
    }


def build_fault_matrix(records, *, experiment_id=None, fault_case=None) -> dict:
    """Build a fault matrix with exactly one row per trial record.

    Older captures that predate the passive ACK fields are accepted unchanged;
    their absent fields simply project to ``None``.
    """
    rows = [fault_matrix_row(record) for record in records]
    return {
        "schema_version": FAULT_MATRIX_SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "experiment_id": experiment_id,
        "fault_case": fault_case,
        "generated_at_utc": _utc_now_iso(),
        "columns": list(FAULT_MATRIX_FIELDS),
        "row_count": len(rows),
        "rows": rows,
    }


def load_trials_jsonl(path: Path) -> list:
    records = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    return records


def write_fault_matrix(
    out_dir: Path, records, *, experiment_id=None, fault_case=None
) -> dict:
    matrix = build_fault_matrix(
        records, experiment_id=experiment_id, fault_case=fault_case
    )
    write_json_atomic(Path(out_dir) / FAULT_MATRIX_FILENAME, matrix)
    return matrix


# -- trial planning ----------------------------------------------------------


class TrialSpec:
    def __init__(self, index: int, pair_index: int, requested_state: str, fault_case=None):
        self.index = index
        self.pair_index = pair_index
        self.requested_state = requested_state
        self.fault_case = fault_case

    @property
    def sequence_position(self) -> str:
        return "first" if self.index % 2 == 1 else "second"

    @property
    def request(self) -> str:
        if self.requested_state == REQUESTED_OFF:
            return guarded.REQUEST_OFF
        return guarded.REQUEST_ON

    @property
    def hint_state(self) -> str:
        if self.requested_state == REQUESTED_OFF:
            return guarded.STATE_FALSE
        return guarded.STATE_TRUE


def build_trial_specs(pairs: int) -> list:
    """Odd trials request OFF, even trials request ON (an ON/OFF pair)."""
    specs = []
    for index in range(1, pairs * 2 + 1):
        pair_index = (index + 1) // 2
        requested = REQUESTED_OFF if index % 2 == 1 else REQUESTED_ON
        specs.append(TrialSpec(index, pair_index, requested))
    return specs


def protocol_trial_specs(args):
    if args.pairs < 1:
        raise ValueError("--pairs must be >= 1")
    specs = build_trial_specs(args.pairs)
    states, labels = args.trial_states, args.trial_fault_cases
    if (states is None) != (labels is None):
        raise ValueError("--trial-states and --trial-fault-cases must be supplied together")
    if states is not None:
        if len(states) != len(specs) or len(labels) != len(specs):
            raise ValueError("states and fault labels must each contain pairs * 2 values")
        if any(state not in ("on", "off") for state in states):
            raise ValueError("trial states must be on/off")
        if any(not label.strip() for label in labels):
            raise ValueError("fault labels must be non-empty")
        specs = [TrialSpec(i + 1, i // 2 + 1, state, labels[i])
                 for i, state in enumerate(states)]
    if not args.fault_case.strip():
        raise ValueError("fault label must be non-empty")
    if (not math.isfinite(args.ack_observation_window)
            or not 0 < args.ack_observation_window <= 30):
        raise ValueError("ACK observation window must be > 0 and <= 30 seconds")
    return specs


def default_observe_fn() -> str:
    prompt = "Observed physical state [on/off/not_observed/contradicted]: "
    while True:
        try:
            answer = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("")
            return "not_observed"
        if answer in OBSERVATIONS:
            return answer
        print("Please enter one of:", ", ".join(OBSERVATIONS))


# -- campaign ----------------------------------------------------------------


class PilotCampaign:
    """Runs the ordered guarded trials and records each one."""

    def __init__(
        self,
        *,
        harness,
        hub: TimingHub,
        out_dir: Path,
        specs,
        dry_run: bool,
        confirm_fn,
        observe_fn,
        mqtt_observer_status: str,
        verbose: bool = True,
        fault_case: str = DEFAULT_FAULT_CASE,
        late_response=None,
        passive_subscriber=None,
        ack_observation_window_seconds=DEFAULT_ACK_WINDOW_SECONDS,
    ):
        self.harness = harness
        self.hub = hub
        self.out_dir = out_dir
        self.specs = list(specs)
        self.dry_run = dry_run
        self.confirm_fn = confirm_fn
        self.observe_fn = observe_fn
        self.mqtt_observer_status = mqtt_observer_status
        self.verbose = verbose
        self.fault_case = fault_case
        # Optional out-of-band response injected after the driver returns. It is
        # recorded passively only; it never changes the driver result.
        self.late_response = late_response
        self.passive_subscriber = passive_subscriber
        self.ack_observation_window_seconds = ack_observation_window_seconds
        self.trials_path = out_dir / TRIALS_FILENAME
        self.records = []
        self.interrupted = False

    # -- run -------------------------------------------------------------

    def run(self) -> dict:
        started_at = _utc_now_iso()
        runtime_before = self.harness.evidence.runtime_invocations
        for spec in self.specs:
            try:
                record = self._run_trial(spec)
            except KeyboardInterrupt:
                self.interrupted = True
                break
            self.records.append(record)
            append_jsonl(self.trials_path, record)
        finished_at = _utc_now_iso()
        summary = self._build_summary(started_at, finished_at, runtime_before)
        write_json_atomic(self.out_dir / "summary.json", summary)
        self._write_operator_notes(summary)
        self._write_fault_matrix()
        return summary

    def _write_fault_matrix(self) -> dict:
        return write_fault_matrix(
            self.out_dir,
            self.records,
            experiment_id=self.out_dir.name,
            fault_case=self.fault_case,
        )

    # -- one trial -------------------------------------------------------

    def _run_trial(self, spec: TrialSpec) -> dict:
        clock = self.hub.begin()
        if self.passive_subscriber is not None:
            self.passive_subscriber.begin_trial()
        t0 = _now_ns()
        started_at = _utc_now_iso()

        state_before = self.harness.state_projection()
        runtime_before = self.harness.evidence.runtime_invocations

        t_decision = None
        t_prep_in = t_prep_out = None
        t_confirm_in = t_confirm_out = None

        decision = self.harness.resolve(spec.request, spec.hint_state)
        t_decision = _now_ns()

        prepared = None
        cancel_result = None
        confirmation_result = None
        confirmation_submitted = False
        outcome = None

        if decision is None:
            outcome = OUTCOME_DECISION_UNAVAILABLE
        elif getattr(decision, "status", None) != EXECUTABLE_CANDIDATE:
            outcome = OUTCOME_REFUSED
        else:
            t_prep_in = _now_ns()
            prepared = self.harness.gate.prepare(decision)
            t_prep_out = _now_ns()
            if getattr(prepared, "status", None) != GATE_STATUS_CONFIRMATION_REQUIRED:
                outcome = OUTCOME_PREPARE_FAILED
            else:
                if self.verbose:
                    self.harness.display(
                        "TRIAL %d/%d  %s  (pair %d, %s)"
                        % (
                            spec.index,
                            len(self.specs),
                            spec.requested_state.upper(),
                            spec.pair_index,
                            spec.sequence_position,
                        ),
                        spec.request,
                        decision,
                        prepared,
                    )
                if self.dry_run:
                    cancel_result = self.harness.gate.cancel(
                        prepared.confirmation_id
                    )
                    outcome = OUTCOME_DRY_RUN
                else:
                    try:
                        submitted = bool(self.confirm_fn())
                    except (EOFError, KeyboardInterrupt):
                        print("")
                        submitted = False
                    if not submitted:
                        cancel_result = self.harness.gate.cancel(
                            prepared.confirmation_id
                        )
                        outcome = OUTCOME_DECLINED
                    else:
                        confirmation_submitted = True
                        t_confirm_in = _now_ns()
                        confirmation_result = self.harness.confirm(prepared)
                        t_confirm_out = _now_ns()
                        if self.verbose:
                            self.harness.report_gate(
                                "trial-%d" % spec.index, confirmation_result
                            )
                        if (
                            getattr(confirmation_result, "status", None)
                            == GATE_STATUS_EXECUTED
                        ):
                            outcome = OUTCOME_EXECUTED
                        else:
                            outcome = OUTCOME_EXECUTION_FAILED

        # The guarded call above has returned. Mark the driver boundary and
        # passively record any out-of-band (late) response. Both are recording
        # only and never change the outcome already determined.
        self.hub.mark_driver_returned()
        if self.late_response is not None:
            self.hub.observe_late_response(self.late_response)

        state_after = self.harness.state_projection()
        runtime_delta = self.harness.evidence.runtime_invocations - runtime_before
        passive_observation = None
        if self.passive_subscriber is not None:
            passive_observation = self.passive_subscriber.finish_trial(
                self.ack_observation_window_seconds
            )

        observation = None
        if not self.dry_run:
            observation = self._observe()

        observer_attached = (
            self.mqtt_observer_status == MQTT_OBSERVER_ATTACHED
        )
        ack_fields = derive_observation_fields(
            passive_observation if self.passive_subscriber is not None else self.hub.observation,
            fault_case=spec.fault_case if spec.fault_case is not None else self.fault_case,
            requested_state=spec.requested_state,
            outcome=outcome,
            observer_attached=observer_attached,
        )
        latencies, timing_notes = _derive_latencies(
            outcome,
            t0,
            t_decision,
            t_prep_in,
            t_prep_out,
            t_confirm_in,
            t_confirm_out,
            clock.marks,
            observer_attached,
        )

        record = {
            "schema_version": SCHEMA_VERSION,
            "tool": TOOL_NAME,
            "trial_index": spec.index,
            "ack_observation_window_seconds": self.ack_observation_window_seconds,
            "ack_observation_mode": "independent_subscriber" if self.passive_subscriber else "driver_calls_only",
            "pair_index": spec.pair_index,
            "sequence_position": spec.sequence_position,
            "requested_state": spec.requested_state,
            "request_text": spec.request,
            "hint_state": spec.hint_state,
            "started_at_utc": started_at,
            "state_before": state_before,
            "state_after": state_after,
            "decision": _decision_summary(decision),
            "prepare": _gate_summary(prepared),
            "cancel_result": _gate_summary(cancel_result),
            "confirmation_submitted": confirmation_submitted,
            "confirmation_result": _gate_summary(confirmation_result),
            "operator_observation": observation,
            "outcome": outcome,
            "runtime_invocations_delta": runtime_delta,
            "runtime_events": list(clock.events),
            "mqtt_observer": self.mqtt_observer_status,
            "latency_basis": LATENCY_BASIS,
            "latencies": latencies,
            "timing_notes": timing_notes,
            "disclaimer": DISCLAIMER,
            **ack_fields,
        }
        self.hub.finish_trial()
        return record

    def _observe(self) -> str:
        try:
            observation = self.observe_fn()
        except (EOFError, KeyboardInterrupt):
            print("")
            return "not_observed"
        if observation not in OBSERVATIONS:
            return "not_observed"
        return observation

    # -- summary ---------------------------------------------------------

    def _build_summary(self, started_at, finished_at, runtime_before) -> dict:
        outcomes = {}
        observations = {name: 0 for name in OBSERVATIONS}
        observation_match = 0
        observation_mismatch = 0
        notes = set()

        for record in self.records:
            outcome = record.get("outcome")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

            observation = record.get("operator_observation")
            if observation in observations:
                observations[observation] += 1
            if observation in (REQUESTED_ON, REQUESTED_OFF):
                if observation == record.get("requested_state"):
                    observation_match += 1
                else:
                    observation_mismatch += 1

            for note in record.get("timing_notes", []):
                notes.add(note)

        runtime_after = self.harness.evidence.runtime_invocations
        return {
            "schema_version": SCHEMA_VERSION,
            "tool": TOOL_NAME,
            "experiment_id": self.out_dir.name,
            "dry_run": self.dry_run,
            "ack_observation_window_seconds": self.ack_observation_window_seconds,
            "interrupted": self.interrupted,
            "started_at_utc": started_at,
            "finished_at_utc": finished_at,
            "mqtt_observer": self.mqtt_observer_status,
            "planned_trials": len(self.specs),
            "trials_recorded": len(self.records),
            "outcomes": outcomes,
            "runtime_invocations_total": runtime_after,
            "runtime_invocations_this_run": runtime_after - runtime_before,
            "runtime_invocations_delta_sum": sum(
                record.get("runtime_invocations_delta", 0)
                for record in self.records
            ),
            "operator_observations": observations,
            "operator_observation_vs_request": {
                "match": observation_match,
                "mismatch": observation_mismatch,
            },
            "latencies": {
                key: _latency_stats(self.records, key) for key in LATENCY_KEYS
            },
            "timing_notes_unique": sorted(notes),
            "trials_jsonl_sha256": _sha256_file(self.trials_path),
            "disclaimer": DISCLAIMER,
        }

    # -- operator notes --------------------------------------------------

    def _write_operator_notes(self, summary) -> None:
        lines = []
        lines.append("# Thesis MQTT pilot operator notes")
        lines.append("")
        lines.append("Experiment: `%s`" % summary["experiment_id"])
        lines.append("")
        lines.append("- tool: `%s`" % TOOL_NAME)
        lines.append("- dry run: %s" % summary["dry_run"])
        lines.append("- planned trials: %d" % summary["planned_trials"])
        lines.append("- trials recorded: %d" % summary["trials_recorded"])
        lines.append("- interrupted: %s" % summary["interrupted"])
        lines.append("- MQTT observer: %s" % self.mqtt_observer_status)
        lines.append("- latency basis: `%s`" % LATENCY_BASIS)
        lines.append("")
        lines.append("## Disclaimers")
        lines.append("")
        lines.append(DISCLAIMER)
        lines.append("")
        lines.append(
            "Operator observation is a human judgment entered during the run. "
            "It is not derived from software state."
        )
        lines.append("")
        lines.append("## Trials")
        lines.append("")
        lines.append(
            "| # | requested | outcome | confirmation | observation | "
            "end_to_end_ms | mqtt_round_trip_ms |"
        )
        lines.append("| - | - | - | - | - | - | - |")
        for record in self.records:
            latencies = record.get("latencies", {})
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s |"
                % (
                    record.get("trial_index"),
                    record.get("requested_state"),
                    record.get("outcome"),
                    record.get("confirmation_submitted"),
                    record.get("operator_observation"),
                    latencies.get("end_to_end_ms"),
                    latencies.get("mqtt_round_trip_ms"),
                )
            )
        lines.append("")
        lines.append("## Timing notes observed")
        lines.append("")
        notes = summary.get("timing_notes_unique", [])
        if notes:
            for note in notes:
                lines.append("- `%s`" % note)
        else:
            lines.append("- none")
        lines.append("")
        with (self.out_dir / "operator_notes.md").open("w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))


# -- composition and manifest ------------------------------------------------


def compose_runtime(config_path: Path, state_mode: str):
    return guarded.compose_runtime(config_path, state_mode)


def build_manifest(experiment_id, label, notes, config_path, out_path: Path,
                   ack_observation_window_seconds=DEFAULT_ACK_WINDOW_SECONDS) -> dict:
    evidence_paths = [
        str(Path(__file__).resolve()),
        str(Path(guarded.__file__).resolve()),
        str(Path(manifest_tool.__file__).resolve()),
    ]
    namespace = argparse.Namespace(
        experiment_id=experiment_id,
        label=label,
        notes=notes,
        profile=[str(config_path)],
        evidence=evidence_paths,
        firmware=[str(REPO_ROOT / source) for source in FIRMWARE_SOURCES],
        out=str(out_path),
    )
    manifest = manifest_tool.build_manifest(namespace)
    manifest["ack_observation_window_seconds"] = ack_observation_window_seconds
    manifest_tool.write_manifest_atomic(manifest, out_path)
    return manifest


# -- entrypoint --------------------------------------------------------------


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python tools/run_thesis_mqtt_pilot.py",
        description=(
            "Thesis-only quantitative pilot of the guarded JarvisOS ESP32 MQTT "
            "vertical: understanding -> ExecutionGate.prepare -> explicit human "
            "CONFIRM -> ExecutionGate.confirm -> Runtime -> real MQTT -> NanoMQ "
            "-> ESP32 relay_1. Captures per-trial records under "
            "captures/thesis/<experiment_id>/."
        ),
        epilog=(
            "There is no --confirm flag. Every mutation requires typing CONFIRM "
            "in this same running process, because the confirmation store is "
            "in-memory."
        ),
    )
    parser.add_argument(
        "--experiment-id",
        default=DEFAULT_EXPERIMENT_ID,
        help="Experiment identifier; also the default output folder name.",
    )
    parser.add_argument(
        "--label",
        default="Guarded MQTT thesis pilot",
        help="Short human-readable experiment label for the manifest.",
    )
    parser.add_argument(
        "--notes",
        default=None,
        help="Free-form manifest notes (avoid secrets).",
    )
    parser.add_argument(
        "--pairs",
        type=int,
        default=DEFAULT_PAIRS,
        help="Number of ON/OFF pairs (each pair is two trials). Default 10.",
    )
    parser.add_argument(
        "--config",
        default=guarded.DEFAULT_PROFILE,
        help="Declarative MQTT profile used to compose the Runtime.",
    )
    parser.add_argument(
        "--state",
        choices=("fresh", "profile"),
        default="fresh",
        help=(
            "fresh (default) composes without restoring persisted DeviceState; "
            "profile honors the profile's configured state store."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory. Default captures/thesis/<experiment_id>.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Run understanding + prepare + cancel only. Never confirms and "
            "never touches the network."
        ),
    )
    parser.add_argument(
        "--no-mqtt-observer",
        action="store_true",
        help="Disable the passive MQTT publish/response timing observer.",
    )
    parser.add_argument(
        "--fault-case",
        default=DEFAULT_FAULT_CASE,
        help=(
            "Label recorded on every trial and in fault_matrix.json. It is a "
            "diagnostic label only and never changes execution behavior."
        ),
    )
    parser.add_argument(
        "--derive-fault-matrix",
        action="store_true",
        help=(
            "Do not run trials. Read --out-dir/trials.jsonl (including older "
            "captures) and write --out-dir/fault_matrix.json."
        ),
    )
    parser.add_argument("--trial-states", nargs="+", default=None,
                        help="Ordered on/off states; requires pairs * 2 values and --trial-fault-cases.")
    parser.add_argument("--trial-fault-cases", nargs="+", default=None,
                        help="Ordered non-empty per-trial labels; requires --trial-states.")
    parser.add_argument("--ack-observation-window", type=float,
                        default=DEFAULT_ACK_WINDOW_SECONDS,
                        help="Passive post-driver observation seconds; does not change execution timeout.")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    config_path, out_dir = _resolve_args_outdir(args)

    if args.derive_fault_matrix:
        trials_path = out_dir / TRIALS_FILENAME
        if not trials_path.exists():
            print("error: %s not found" % trials_path, file=sys.stderr)
            return 2
        records = load_trials_jsonl(trials_path)
        matrix = write_fault_matrix(
            out_dir,
            records,
            experiment_id=out_dir.name,
            fault_case=args.fault_case,
        )
        print(
            "fault matrix written: %s (%d rows)"
            % (out_dir / FAULT_MATRIX_FILENAME, matrix["row_count"])
        )
        return 0

    try:
        specs = protocol_trial_specs(args)
    except ValueError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    trials_path = out_dir / TRIALS_FILENAME
    if trials_path.exists():
        print(
            "error: %s already exists; choose a new --experiment-id or "
            "--out-dir to avoid mixing runs." % trials_path,
            file=sys.stderr,
        )
        return 2

    print("=" * 68)
    print("THESIS MQTT PILOT")
    print("=" * 68)
    print("experiment   :", args.experiment_id)
    print("profile      :", config_path)
    print("device       :", guarded.DEVICE_ID, guarded.CAPABILITY, guarded.OPERATION)
    print("pairs        :", args.pairs, "(%d trials)" % (args.pairs * 2))
    print("dry run      :", args.dry_run)
    print("output dir   :", out_dir)
    print("safety scope : onboard LED / GPIO2 only")

    try:
        manifest = build_manifest(
            args.experiment_id,
            args.label,
            args.notes,
            config_path,
            out_dir / "manifest.json",
            ack_observation_window_seconds=args.ack_observation_window,
        )
    except Exception as error:
        print("error: could not write manifest: %s" % type(error).__name__, file=sys.stderr)
        return 2
    manifest_errors = manifest.get("errors") or []
    if manifest_errors:
        print(
            "warning: %d manifest hash error(s) recorded" % len(manifest_errors),
            file=sys.stderr,
        )

    try:
        runtime, state_note = compose_runtime(config_path, args.state)
    except Exception as error:
        print("error: could not compose runtime: %s" % type(error).__name__, file=sys.stderr)
        return 2
    print("state store  :", state_note)

    evidence = guarded.Evidence()
    harness = guarded.GuardedHardwareValidation(runtime, evidence)

    hub = TimingHub()
    bus = getattr(runtime.context, "event_bus", None)
    if bus is not None:
        timer = EventTimer(hub)
        for event_type in (
            COMMAND_EXECUTION_STARTED_EVENT,
            CAPABILITY_EXECUTION_COMPLETED_EVENT,
            CAPABILITY_EXECUTION_FAILED_EVENT,
        ):
            try:
                bus.subscribe(event_type, timer)
            except Exception:
                pass

    if args.no_mqtt_observer:
        observer_status = MQTT_OBSERVER_NOT_ATTACHED
    else:
        observer_status = attach_mqtt_observer(runtime, hub)
    print("mqtt observer:", observer_status)

    passive_subscriber = None
    if not args.dry_run and not args.no_mqtt_observer:
        try:
            passive_subscriber = start_passive_ack_subscriber(runtime, args.ack_observation_window)
        except Exception as error:
            runtime.shutdown()
            print("error: passive observer unavailable: %s" % type(error).__name__, file=sys.stderr)
            return 2
    campaign = PilotCampaign(
        harness=harness,
        hub=hub,
        out_dir=out_dir,
        specs=specs,
        dry_run=args.dry_run,
        confirm_fn=harness.prompt,
        observe_fn=default_observe_fn,
        mqtt_observer_status=observer_status,
        fault_case=args.fault_case,
        passive_subscriber=passive_subscriber,
        ack_observation_window_seconds=args.ack_observation_window,
    )

    summary = None
    try:
        summary = campaign.run()
    finally:
        if passive_subscriber is not None:
            passive_subscriber.close()
        try:
            runtime.shutdown()
        except Exception:
            pass

    _print_summary(summary, out_dir)

    if campaign.interrupted:
        return 1
    if len(campaign.records) != len(specs):
        return 1
    if not all(
        record.get("outcome") in SUCCESS_OUTCOMES for record in campaign.records
    ):
        return 1
    return 0


def _resolve_args_outdir(args):
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (REPO_ROOT / config_path).resolve()
    out_dir = Path(args.out_dir) if getattr(args, "out_dir", None) else None
    if out_dir is None:
        out_dir = Path(DEFAULT_OUTPUT_ROOT) / args.experiment_id
    if not out_dir.is_absolute():
        out_dir = (REPO_ROOT / out_dir).resolve()
    return config_path, out_dir


def _print_summary(summary, out_dir):
    if summary is None:
        print("")
        print("no summary was produced.")
        return
    print("")
    print("=" * 68)
    print("PILOT SUMMARY")
    print("=" * 68)
    print("recorded trials:", summary["trials_recorded"])
    print("outcomes       :", summary.get("outcomes"))
    print("observations   :", summary.get("operator_observations"))
    for key in LATENCY_KEYS:
        stats = summary["latencies"].get(key, {})
        print(
            "  %-20s n=%s null=%s"
            % (key, stats.get("count"), stats.get("null_count"))
        )
    print("output dir     :", out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
