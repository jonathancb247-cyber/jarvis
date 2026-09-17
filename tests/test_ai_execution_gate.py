"""Focused tests for the confirmation-gated safe local understanding execution gate.

These tests prove the corrective execution vertical invariants:

- ``prepare`` only validates and binds a pending confirmation; it NEVER calls
  Runtime (``Runtime.execute`` call count after prepare is zero).
- Every validated candidate requires explicit ``confirm`` before any mutation
  reaches Runtime, regardless of the AI-provided ``confirmation_required``.
- ``confirm`` re-validates the exact stored plan (plan-digest binding, single
  use, TOCTOU device/capability re-check) before the single Runtime execute.
- ``commands_executed`` is honest and exact: False for confirmation_required,
  rejected, cancelled, or failed-before-invocation; True only when Runtime was
  invoked.
- The strict v1 allowlist accepts exactly ``power.switch`` with
  ``{"state": "true"}`` or ``{"state": "false"}`` and never broadens values.
- Raw exceptions and DriverResult internals are never exposed.
- AST-level import boundary enforcement is retained.
"""

import ast
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import threading
import unittest

from jarvis_core.ai.confirmation import AIConfirmationStore, plan_digest
from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
    AI_CONFIRMATION_REQUIRED,
    AI_EXECUTION_NOT_CONFIRMED,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
    PLAN_SCHEMA_VERSION,
    AIActionPlan,
    AIActionStep,
    AIClarification,
    AIRefusal,
)
from jarvis_core.ai.context import SafeContextBuilder
from jarvis_core.ai.execution_gate import (
    ALLOWED_CAPABILITIES,
    ALLOWED_POWER_SWITCH_STATES,
    EXECUTION_GATE_SOURCE,
    GATE_STATUS_CANCELLED,
    GATE_STATUS_CONFIRMATION_REQUIRED,
    GATE_STATUSES,
    GATE_STATUS_EXECUTED,
    GATE_STATUS_EXECUTION_FAILED,
    GATE_STATUS_REJECTED,
    REJECT_CAPABILITY_UNAVAILABLE,
    REJECT_CONFIRMATION_DIGEST_MISMATCH,
    REJECT_CONFIRMATION_NOT_FOUND,
    REJECT_DECISION_NOT_EXECUTABLE,
    REJECT_DEVICE_UNAVAILABLE,
    REJECT_INVALID_ARGUMENTS,
    REJECT_INVALID_COMMAND,
    REJECT_MESSAGE,
    REJECT_MULTI_STEP_PLAN,
    REJECT_UNSUPPORTED_CAPABILITY,
    REJECT_UNSUPPORTED_DECISION,
    REJECT_REVALIDATION_FAILED,
    RUNTIME_EXECUTION_FAILED,
    RUNTIME_FAILURE_MESSAGE,
    RUNTIME_RESULT_INVALID,
    RUNTIME_RESULT_MESSAGE,
    ExecutionGate,
    ExecutionGateResult,
)
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    FAILURE_STAGE_PROVIDER_REQUEST,
    FAILURE_STAGE_RESOLVER,
    LOCAL_AI_UNAVAILABLE,
    NEEDS_CLARIFICATION,
    REFUSED,
    UNDERSTANDING_FAILED,
    LocalUnderstandingDecision,
    decide_understanding,
)
from jarvis_core.bootstrap import build_http_runtime
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry
from jarvis_core.domain import CapabilityResult, Command
from jarvis_core.drivers import DriverResult, SimulatedDriver
from jarvis_core.planner import (
    APPLY_OPERATION,
    DEVICE_EXECUTE_COMMAND,
    Planner,
)
from tools.ai_execution_gate import (
    build_argument_parser,
    format_gate_text_payload,
    run_ai_execution_gate,
)


class RecordingSimulatedDriver(SimulatedDriver):
    def __init__(self):
        super().__init__()
        self.read_calls = 0
        self.apply_calls = 0
        self.last_parameters = None

    def read(self, device, capability_name):
        self.read_calls += 1
        return DriverResult(True, {"power": False}, None)

    def apply(self, device, capability_name, parameters):
        self.apply_calls += 1
        self.last_parameters = parameters.copy()
        return DriverResult(
            True,
            {"power": parameters.get("state") == "true"},
            None,
        )


class FailingApplyDriver(RecordingSimulatedDriver):
    def apply(self, device, capability_name, parameters):
        self.apply_calls += 1
        self.last_parameters = parameters.copy()
        return DriverResult(False, {}, "simulated_failure")


class RecordingRuntime:
    """Runtime spy carrying a real DeviceRegistry for availability checks."""

    def __init__(self, result=None, devices=()):
        registry = DeviceRegistry()
        for device in devices:
            registry.register(device)
        self.context = SimpleNamespace(device_registry=registry)
        self.executions = []
        self.result = result or CapabilityResult(
            success=True,
            message="ok",
            data={
                "device_id": "lamp_1",
                "capability": "power.switch",
                "operation": APPLY_OPERATION,
            },
        )

    def execute(self, command, correlation_id=None):
        self.executions.append(command)
        return self.result


class RaisingRuntime(RecordingRuntime):
    def execute(self, command, correlation_id=None):
        self.executions.append(command)
        raise RuntimeError("boom")


class FlippingPlanner:
    def __init__(self):
        self.calls = 0

    def plan(self, text, source="cli"):
        self.calls += 1
        if self.calls <= 1:
            return Planner().plan(text, source=source)
        return Command(name="unknown", args={"text": text}, source=source)


class PlannerRaisesOnReplan:
    def __init__(self, error):
        self.calls = 0
        self.error = error

    def plan(self, text, source="cli"):
        self.calls += 1
        if self.calls <= 1:
            return Planner().plan(text, source=source)
        raise self.error


class NoneReturningRuntime(RecordingRuntime):
    def execute(self, command, correlation_id=None):
        self.executions.append(command)
        return None


class WeirdReturningRuntime(RecordingRuntime):
    def execute(self, command, correlation_id=None):
        self.executions.append(command)
        return object()


class MalformedCapabilityRuntime(RecordingRuntime):
    def execute(self, command, correlation_id=None):
        self.executions.append(command)
        return CapabilityResult(success=None, message=None, error="oops")


class ExecutionGateResultInvariantTests(unittest.TestCase):
    def test_statuses_and_allowlist_are_explicit(self):
        self.assertEqual(
            GATE_STATUSES,
            frozenset(
                {
                    GATE_STATUS_CONFIRMATION_REQUIRED,
                    GATE_STATUS_EXECUTED,
                    GATE_STATUS_EXECUTION_FAILED,
                    GATE_STATUS_REJECTED,
                    GATE_STATUS_CANCELLED,
                }
            ),
        )
        self.assertEqual(ALLOWED_CAPABILITIES, frozenset({"power.switch"}))
        self.assertEqual(ALLOWED_POWER_SWITCH_STATES, frozenset({"true", "false"}))

    def test_result_is_immutable(self):
        runtime = RecordingRuntime(devices=[room_lamp()])
        result = ExecutionGate(runtime).prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        with self.assertRaises(FrozenInstanceError):
            result.status = GATE_STATUS_EXECUTED

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status="unknown",
                success=False,
                commands_executed=False,
            )

    def test_confirmation_required_shape_is_enforced(self):
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_CONFIRMATION_REQUIRED,
                success=True,
                commands_executed=False,
                confirmation_id="c",
                plan_digest="d",
            )
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_CONFIRMATION_REQUIRED,
                success=False,
                commands_executed=True,
                confirmation_id="c",
                plan_digest="d",
            )
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_CONFIRMATION_REQUIRED,
                success=False,
                commands_executed=False,
            )

    def test_executed_shape_is_enforced(self):
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_EXECUTED,
                success=True,
                commands_executed=True,
                runtime_result=CapabilityResult(True, "ok"),
            )
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_EXECUTED,
                success=True,
                commands_executed=True,
                runtime_result=CapabilityResult(True, "ok"),
                confirmation_id="c",
                plan_digest="d",
                device_id="lamp_1",
                capability="power.switch",
                arguments={"state": "true"},
                error="nope",
            )
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_EXECUTED,
                success=True,
                commands_executed=True,
                runtime_result=CapabilityResult(True, "ok"),
                confirmation_id="c",
                plan_digest="d",
                device_id="lamp_1",
                capability="power.switch",
                arguments={"state": "true"},
                reason=REJECT_MULTI_STEP_PLAN,
            )

    def test_execution_failed_shape_is_enforced(self):
        failed = CapabilityResult(False, "nope", error="device_execution_failed")
        valid = ExecutionGateResult(
            status=GATE_STATUS_EXECUTION_FAILED,
            success=False,
            commands_executed=True,
            device_id="lamp_1",
            capability="power.switch",
            arguments={"state": "true"},
            confirmation_id="c",
            plan_digest="d",
            runtime_result=failed,
            error="device_execution_failed",
            message="nope",
        )
        self.assertEqual(valid.status, GATE_STATUS_EXECUTION_FAILED)
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_EXECUTION_FAILED,
                success=False,
                commands_executed=True,
                device_id="lamp_1",
                capability="power.switch",
                arguments={"state": "true"},
                confirmation_id="c",
                plan_digest="d",
                runtime_result=failed,
                error="some_other_error",
                message="nope",
            )

    def test_rejected_and_cancelled_shapes_are_enforced(self):
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_REJECTED,
                success=False,
                commands_executed=False,
                reason="nope",
            )
        cancelled_result = ExecutionGateResult(
            status=GATE_STATUS_CANCELLED,
            success=False,
            commands_executed=False,
            confirmation_id="c",
            plan_digest="d",
            error=AI_EXECUTION_NOT_CONFIRMED,
            message="cancelled",
        )
        self.assertEqual(cancelled_result.status, GATE_STATUS_CANCELLED)
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_CANCELLED,
                success=False,
                commands_executed=False,
                confirmation_id="c",
                plan_digest="d",
                error="wrong_error",
            )
        with self.assertRaises(ValueError):
            ExecutionGateResult(
                status=GATE_STATUS_CANCELLED,
                success=False,
                commands_executed=False,
                error=AI_EXECUTION_NOT_CONFIRMED,
            )


class ExecutionGatePrepareRequiresConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.runtime = RecordingRuntime(devices=[room_lamp()])
        self.gate = ExecutionGate(self.runtime)

    def test_prepare_returns_confirmation_required_and_never_executes(self):
        result = self.gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        self.assertEqual(result.status, GATE_STATUS_CONFIRMATION_REQUIRED)
        self.assertIs(result.success, False)
        self.assertIs(result.commands_executed, False)
        self.assertTrue(result.confirmation_id)
        self.assertTrue(result.plan_digest)
        self.assertEqual(result.error, AI_CONFIRMATION_REQUIRED)
        self.assertIsNone(result.runtime_result)
        self.assertEqual(self.runtime.executions, [])

    def test_prepare_binds_one_pending_confirmation_with_digest(self):
        decision = executable_decision("device apply lamp_1 power.switch state=true")
        result = self.gate.prepare(decision)

        self.assertEqual(
            self.gate.confirmation_store.pending.pending_plan_id,
            result.confirmation_id,
        )
        self.assertEqual(
            self.gate.confirmation_store.pending.normalized_plan_digest,
            result.plan_digest,
        )
        self.assertEqual(result.plan_digest, plan_digest(decision.plan))

    def test_incoming_confirmation_required_false_cannot_bypass(self):
        decision = executable_decision(
            "device apply lamp_1 power.switch state=true",
            confirmation_required=False,
        )
        result = self.gate.prepare(decision)

        self.assertEqual(result.status, GATE_STATUS_CONFIRMATION_REQUIRED)
        self.assertIs(self.runtime.executions == [], True)

    def test_prepare_records_exact_derived_request_fields(self):
        result = self.gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        self.assertEqual(result.device_id, "lamp_1")
        self.assertEqual(result.capability, "power.switch")
        self.assertEqual(result.arguments, {"state": "true"})


class ExecutionGatePrepareRejectedPathTests(unittest.TestCase):
    def setUp(self):
        self.runtime = RecordingRuntime(devices=[room_lamp()])

    def assert_prepare_rejected(self, decision, expected_reason):
        gate = ExecutionGate(self.runtime)
        result = gate.prepare(decision)
        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertIs(result.commands_executed, False)
        self.assertEqual(result.reason, expected_reason)
        self.assertIsNone(result.runtime_result)
        self.assertIsNone(result.confirmation_id)
        self.assertIsNone(result.plan_digest)
        self.assertIsNone(gate.confirmation_store.pending)
        self.assertEqual(
            self.runtime.executions,
            [],
            "rejected decisions must never reach Runtime",
        )

    def test_clarify_decision_never_creates_confirmation(self):
        self.assert_prepare_rejected(clarify_decision(), REJECT_DECISION_NOT_EXECUTABLE)

    def test_refused_decision_never_creates_confirmation(self):
        self.assert_prepare_rejected(refused_decision(), REJECT_DECISION_NOT_EXECUTABLE)

    def test_unavailable_decision_never_creates_confirmation(self):
        self.assert_prepare_rejected(
            unavailable_decision(),
            REJECT_DECISION_NOT_EXECUTABLE,
        )

    def test_failed_decision_never_creates_confirmation(self):
        self.assert_prepare_rejected(failed_decision(), REJECT_DECISION_NOT_EXECUTABLE)

    def test_malformed_input_is_rejected(self):
        self.assert_prepare_rejected(None, REJECT_UNSUPPORTED_DECISION)
        self.assert_prepare_rejected({"status": EXECUTABLE_CANDIDATE}, REJECT_UNSUPPORTED_DECISION)

    def test_multi_step_plan_is_rejected(self):
        plan = AIActionPlan(
            schema_version=PLAN_SCHEMA_VERSION,
            kind=PLAN_KIND_EXECUTE,
            steps=(
                AIActionStep(
                    index=0,
                    canonical_command_text="device apply lamp_1 power.switch state=true",
                    safe_description="First step.",
                    target_device_id="lamp_1",
                    capability_name="power.switch",
                    action_kind=ACTION_KIND_MUTATE,
                ),
                AIActionStep(
                    index=1,
                    canonical_command_text="device apply lamp_1 power.switch state=false",
                    safe_description="Second step.",
                    target_device_id="lamp_1",
                    capability_name="power.switch",
                    action_kind=ACTION_KIND_MUTATE,
                ),
            ),
            safe_summary="Two-step plan.",
            confirmation_required=True,
        )
        decision = LocalUnderstandingDecision(
            provider_id="p",
            model_id="m",
            status=EXECUTABLE_CANDIDATE,
            proposal_valid=True,
            resolver_kind=PLAN_KIND_EXECUTE,
            planner_kind=DEVICE_EXECUTE_COMMAND,
            plan=plan,
            commands_executed=False,
        )
        self.assert_prepare_rejected(decision, REJECT_MULTI_STEP_PLAN)

    def test_unsupported_capability_is_rejected(self):
        self.assert_prepare_rejected(
            executable_decision(
                "device apply lamp_1 status.read state=true",
                target="lamp_1",
                capability="status.read",
            ),
            REJECT_UNSUPPORTED_CAPABILITY,
        )

    def test_read_operation_is_not_gated_for_execution_in_v1(self):
        self.assert_prepare_rejected(
            executable_decision(
                "device read lamp_1 power.switch",
                target="lamp_1",
                capability="power.switch",
            ),
            REJECT_UNSUPPORTED_CAPABILITY,
        )

    def test_wrong_command_name_is_rejected(self):
        self.assert_prepare_rejected(
            executable_decision("time now"),
            REJECT_INVALID_COMMAND,
        )

    def test_misleading_step_capability_is_rejected(self):
        self.assert_prepare_rejected(
            executable_decision(
                "device apply lamp_1 power.switch state=true",
                target="lamp_1",
                capability="status.read",
            ),
            REJECT_INVALID_COMMAND,
        )

    def test_misleading_step_device_is_rejected(self):
        self.assert_prepare_rejected(
            executable_decision(
                "device apply lamp_2 power.switch state=true",
                target="lamp_1",
                capability="power.switch",
            ),
            REJECT_INVALID_COMMAND,
        )

    def test_extra_argument_is_rejected(self):
        self.assert_prepare_rejected(
            executable_decision(
                "device apply lamp_1 power.switch state=true brightness=5"
            ),
            REJECT_INVALID_ARGUMENTS,
        )

    def test_missing_argument_is_rejected(self):
        self.assert_prepare_rejected(
            executable_decision("device apply lamp_1 power.switch"),
            REJECT_INVALID_ARGUMENTS,
        )

    def test_wrong_parameter_key_is_rejected(self):
        self.assert_prepare_rejected(
            executable_decision("device apply lamp_1 power.switch brightness=5"),
            REJECT_INVALID_ARGUMENTS,
        )

    def test_invalid_state_values_are_rejected(self):
        for raw_state in ("maybe", "on", "off"):
            with self.subTest(state=raw_state):
                self.assert_prepare_rejected(
                    executable_decision(
                        f"device apply lamp_1 power.switch state={raw_state}"
                    ),
                    REJECT_INVALID_ARGUMENTS,
                )

    def test_unsafe_shell_command_never_reaches_runtime(self):
        self.assert_prepare_rejected(
            executable_decision("device apply lamp_1 power.switch state=true; rm -rf"),
            REJECT_INVALID_COMMAND,
        )

    def test_newline_injection_never_reaches_runtime(self):
        self.assert_prepare_rejected(
            executable_decision(
                "device apply lamp_1 power.switch state=true\ndevice list"
            ),
            REJECT_INVALID_COMMAND,
        )

    def test_fabricated_device_missing_from_registry_is_rejected(self):
        isolated = RecordingRuntime(devices=[])
        result = ExecutionGate(isolated).prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        self.assertEqual(result.reason, REJECT_DEVICE_UNAVAILABLE)
        self.assertEqual(isolated.executions, [])

    def test_device_without_action_capability_is_rejected(self):
        reading_only = RecordingRuntime(devices=[reading_only_lamp()])
        result = ExecutionGate(reading_only).prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        self.assertEqual(result.reason, REJECT_CAPABILITY_UNAVAILABLE)
        self.assertEqual(reading_only.executions, [])


class ExecutionGateConfirmTests(unittest.TestCase):
    def setUp(self):
        self.runtime = RecordingRuntime(devices=[room_lamp()])
        self.gate = ExecutionGate(self.runtime)

    def prepared(self, command="device apply lamp_1 power.switch state=true"):
        return self.gate.prepare(executable_decision(command))

    def test_confirm_executes_exactly_once_with_derived_command(self):
        prepared = self.prepared()

        result = self.gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTED)
        self.assertIs(result.success, True)
        self.assertIs(result.commands_executed, True)
        self.assertTrue(result.runtime_result.success)
        self.assertEqual(len(self.runtime.executions), 1)
        command = self.runtime.executions[0]
        self.assertEqual(command.name, DEVICE_EXECUTE_COMMAND)
        self.assertEqual(command.source, EXECUTION_GATE_SOURCE)
        self.assertEqual(
            command.args,
            {
                "device_id": "lamp_1",
                "capability": "power.switch",
                "operation": APPLY_OPERATION,
                "parameters": {"state": "true"},
            },
        )

    def test_spanish_on_light_executes_and_turns_on_after_confirm(self):
        runtime = build_http_runtime(RecordingSimulatedDriver(), devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(run_decision("Enciende la luz del cuarto.", runtime))

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTED)
        self.assertEqual(result.arguments, {"state": "true"})
        self.assertIs(
            runtime.context.device_registry.get("lamp_1").state.properties["power"],
            True,
        )

    def test_spanish_off_light_executes_and_turns_off_after_confirm(self):
        runtime = build_http_runtime(RecordingSimulatedDriver(), devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(run_decision("Apaga la luz del cuarto.", runtime))

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTED)
        self.assertEqual(result.arguments, {"state": "false"})
        self.assertIs(
            runtime.context.device_registry.get("lamp_1").state.properties["power"],
            False,
        )

    def test_decision_surface_never_claims_execution_after_confirm(self):
        runtime = build_http_runtime(RecordingSimulatedDriver(), devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        decision = run_decision("Enciende la luz del cuarto.", runtime)
        prepared = gate.prepare(decision)
        gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(decision.status, EXECUTABLE_CANDIDATE)
        self.assertIs(decision.commands_executed, False)

    def test_unknown_confirmation_id_is_rejected_without_execution(self):
        prepared = self.prepared()

        result = self.gate.confirm("not-the-confirmation-id", prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_CONFIRMATION_NOT_FOUND)
        self.assertIs(result.commands_executed, False)
        self.assertEqual(self.runtime.executions, [])

    def test_wrong_plan_digest_is_rejected_without_execution(self):
        prepared = self.prepared()
        wrong_digest = "0" * 64

        result = self.gate.confirm(prepared.confirmation_id, wrong_digest)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_CONFIRMATION_DIGEST_MISMATCH)
        self.assertIs(result.commands_executed, False)
        self.assertEqual(self.runtime.executions, [])
        self.assertIsNone(self.gate.confirmation_store.pending)

    def test_confirmation_is_single_use_and_replay_is_blocked(self):
        prepared = self.prepared()

        first = self.gate.confirm(prepared.confirmation_id, prepared.plan_digest)
        self.assertEqual(first.status, GATE_STATUS_EXECUTED)

        replay = self.gate.confirm(prepared.confirmation_id, prepared.plan_digest)
        self.assertEqual(replay.status, GATE_STATUS_REJECTED)
        self.assertEqual(replay.reason, REJECT_CONFIRMATION_NOT_FOUND)
        self.assertEqual(
            len(self.runtime.executions),
            1,
            "replayed confirmations must never reach Runtime again",
        )

    def test_cancel_prevents_execution(self):
        prepared = self.prepared()

        cancelled = self.gate.cancel(prepared.confirmation_id)

        self.assertEqual(cancelled.status, GATE_STATUS_CANCELLED)
        self.assertIs(cancelled.commands_executed, False)
        self.assertEqual(cancelled.error, AI_EXECUTION_NOT_CONFIRMED)
        self.assertEqual(self.runtime.executions, [])
        self.assertIsNone(self.gate.confirmation_store.pending)

    def test_confirm_after_cancel_is_rejected(self):
        prepared = self.prepared()
        self.gate.cancel(prepared.confirmation_id)

        result = self.gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_CONFIRMATION_NOT_FOUND)
        self.assertEqual(self.runtime.executions, [])

    def test_cancel_unknown_id_is_rejected(self):
        result = self.gate.cancel("not-the-confirmation-id")
        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_CONFIRMATION_NOT_FOUND)
        self.assertEqual(self.runtime.executions, [])

    def test_device_removed_between_prepare_and_confirm_is_rejected(self):
        runtime = build_http_runtime(RecordingSimulatedDriver(), devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        runtime.context.device_registry.unregister("lamp_1")

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_DEVICE_UNAVAILABLE)
        self.assertIs(result.commands_executed, False)
        self.assertIsNone(gate.confirmation_store.pending)

    def test_capability_removed_between_prepare_and_confirm_is_rejected(self):
        driver = RecordingSimulatedDriver()
        runtime = build_http_runtime(driver, devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        runtime.context.device_registry.unregister("lamp_1")
        runtime.context.device_registry.register(reading_only_lamp())

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_CAPABILITY_UNAVAILABLE)
        self.assertIs(result.commands_executed, False)
        self.assertEqual(driver.apply_calls, 0)
        self.assertIsNone(gate.confirmation_store.pending)

    def test_planner_flip_on_confirm_stops_before_runtime(self):
        planner = FlippingPlanner()
        gate = ExecutionGate(self.runtime, planner=planner)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        self.assertEqual(planner.calls, 1)

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_INVALID_COMMAND)
        self.assertEqual(self.runtime.executions, [])
        self.assertIsNone(gate.confirmation_store.pending)

    def test_runtime_device_failure_surfaces_execution_failed(self):
        driver = FailingApplyDriver()
        runtime = build_http_runtime(driver, devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTION_FAILED)
        self.assertIs(result.success, False)
        self.assertIs(result.commands_executed, True)
        self.assertEqual(driver.apply_calls, 1)
        self.assertEqual(result.runtime_result.error, "device_execution_failed")
        self.assertEqual(result.error, result.runtime_result.error)
        self.assertIsNone(result.reason)
        self.assertIsNone(gate.confirmation_store.pending)

    def test_runtime_raise_is_bounded_as_execution_failed(self):
        runtime = RaisingRuntime(devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTION_FAILED)
        self.assertIs(result.commands_executed, True)
        self.assertEqual(result.error, RUNTIME_EXECUTION_FAILED)
        self.assertEqual(result.runtime_result.message, RUNTIME_FAILURE_MESSAGE)
        self.assertEqual(len(runtime.executions), 1)

    def test_plan_digest_binds_confirmation_to_exact_normalized_plan(self):
        prepared = self.prepared()
        other_plan = execute_plan(
            "device apply lamp_1 power.switch state=false",
            target="lamp_1",
            capability="power.switch",
        )

        result = self.gate.confirm(prepared.confirmation_id, plan_digest(other_plan))

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_CONFIRMATION_DIGEST_MISMATCH)
        self.assertEqual(self.runtime.executions, [])

    def test_rejected_confirm_never_exposes_raw_exception(self):
        prepared = self.prepared()
        result = self.gate.confirm(prepared.confirmation_id, "bad")
        self.assertIsNotNone(result.error)
        self.assertIsNone(result.runtime_result)


class ExecutionGateConfirmSafetyTests(unittest.TestCase):
    def setUp(self):
        self.runtime = RecordingRuntime(devices=[room_lamp()])
        self.gate = ExecutionGate(self.runtime)

    def prepared(self, command="device apply lamp_1 power.switch state=true"):
        return self.gate.prepare(executable_decision(command))

    def race_confirm(self, gate, confirmation_id, plan_digest):
        results = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            results.append(gate.confirm(confirmation_id, plan_digest))

        left, right = threading.Thread(target=worker), threading.Thread(target=worker)
        left.start()
        right.start()
        left.join()
        right.join()
        return results

    def test_concurrent_confirm_claims_exactly_once(self):
        prepared = self.prepared()
        results = self.race_confirm(
            self.gate,
            prepared.confirmation_id,
            prepared.plan_digest,
        )

        self.assertEqual(len(results), 2)
        executed = [r for r in results if r.status == GATE_STATUS_EXECUTED]
        rejected = [r for r in results if r.status == GATE_STATUS_REJECTED]
        self.assertEqual(len(executed), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].reason, REJECT_CONFIRMATION_NOT_FOUND)
        self.assertEqual(len(self.runtime.executions), 1)

    def test_concurrent_confirm_with_failing_runtime_claims_once(self):
        runtime = NoneReturningRuntime(devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        results = self.race_confirm(gate, prepared.confirmation_id, prepared.plan_digest)

        statuses = sorted(result.status for result in results)
        self.assertEqual(
            statuses,
            sorted([GATE_STATUS_EXECUTION_FAILED, GATE_STATUS_REJECTED]),
        )
        self.assertEqual(len(runtime.executions), 1)

    def test_confirm_vs_cancel_race_runtime_at_most_once(self):
        for _ in range(10):
            runtime = RecordingRuntime(devices=[room_lamp()])
            gate = ExecutionGate(runtime)
            prepared = gate.prepare(
                executable_decision("device apply lamp_1 power.switch state=true")
            )
            results = []
            barrier = threading.Barrier(2)

            def worker(kind):
                barrier.wait()
                if kind == "confirm":
                    results.append(
                        gate.confirm(prepared.confirmation_id, prepared.plan_digest)
                    )
                else:
                    results.append(gate.cancel(prepared.confirmation_id))

            confirm_thread = threading.Thread(target=worker, args=("confirm",))
            cancel_thread = threading.Thread(target=worker, args=("cancel",))
            confirm_thread.start()
            cancel_thread.start()
            confirm_thread.join()
            cancel_thread.join()

            self.assertLessEqual(len(runtime.executions), 1)
            self.assertIsNone(gate.confirmation_store.pending)
            replay = gate.confirm(prepared.confirmation_id, prepared.plan_digest)
            self.assertEqual(replay.status, GATE_STATUS_REJECTED)
            self.assertEqual(replay.reason, REJECT_CONFIRMATION_NOT_FOUND)

    def test_repeated_concurrent_confirm_never_double_executes(self):
        for _ in range(50):
            runtime = RecordingRuntime(devices=[room_lamp()])
            gate = ExecutionGate(runtime)
            prepared = gate.prepare(
                executable_decision("device apply lamp_1 power.switch state=true")
            )

            results = self.race_confirm(
                gate,
                prepared.confirmation_id,
                prepared.plan_digest,
            )

            self.assertEqual(len(runtime.executions), 1)
            executed = [r for r in results if r.status == GATE_STATUS_EXECUTED]
            rejected = [r for r in results if r.status == GATE_STATUS_REJECTED]
            self.assertEqual(len(executed), 1)
            self.assertEqual(len(rejected), 1)
            self.assertIsNone(gate.confirmation_store.pending)

    def test_planner_exception_in_confirm_is_bounded_and_consumes_token(self):
        gate = ExecutionGate(
            self.runtime,
            planner=PlannerRaisesOnReplan(RuntimeError("sensitive planner detail")),
        )
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        self.assertIsNotNone(gate.confirmation_store.pending)

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_REVALIDATION_FAILED)
        self.assertIs(result.commands_executed, False)
        self.assertEqual(self.runtime.executions, [])
        self.assertIsNone(gate.confirmation_store.pending)
        self.assertEqual(result.message, REJECT_MESSAGE)
        self.assertNotIn("sensitive", str(result))

    def test_unexpected_validation_exception_in_confirm_is_bounded_and_consumes_token(self):
        gate = ExecutionGate(
            self.runtime,
            planner=PlannerRaisesOnReplan(ValueError("sensitive planner detail")),
        )
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_REVALIDATION_FAILED)
        self.assertIs(result.commands_executed, False)
        self.assertEqual(self.runtime.executions, [])
        self.assertIsNone(gate.confirmation_store.pending)
        self.assertNotIn("sensitive", str(result))

    def test_runtime_execute_raise_is_bounded_no_raw_leak(self):
        runtime = RaisingRuntime(devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTION_FAILED)
        self.assertIs(result.commands_executed, True)
        self.assertEqual(result.error, RUNTIME_EXECUTION_FAILED)
        self.assertEqual(result.runtime_result.message, RUNTIME_FAILURE_MESSAGE)
        self.assertEqual(len(runtime.executions), 1)
        self.assertNotIn("boom", str(result))

    def test_runtime_returns_none_is_bounded_execution_failed(self):
        runtime = NoneReturningRuntime(devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTION_FAILED)
        self.assertIs(result.commands_executed, True)
        self.assertEqual(result.error, RUNTIME_RESULT_INVALID)
        self.assertEqual(result.runtime_result.error, RUNTIME_RESULT_INVALID)
        self.assertEqual(len(runtime.executions), 1)

    def test_runtime_returns_arbitrary_object_is_bounded_execution_failed(self):
        runtime = WeirdReturningRuntime(devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTION_FAILED)
        self.assertIs(result.commands_executed, True)
        self.assertEqual(result.error, RUNTIME_RESULT_INVALID)
        self.assertEqual(result.runtime_result.message, RUNTIME_RESULT_MESSAGE)
        self.assertEqual(len(runtime.executions), 1)

    def test_runtime_returns_malformed_capability_result_is_bounded(self):
        runtime = MalformedCapabilityRuntime(devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        prepared = gate.prepare(
            executable_decision("device apply lamp_1 power.switch state=true")
        )

        result = gate.confirm(prepared.confirmation_id, prepared.plan_digest)

        self.assertEqual(result.status, GATE_STATUS_EXECUTION_FAILED)
        self.assertIs(result.commands_executed, True)
        self.assertEqual(result.error, RUNTIME_RESULT_INVALID)
        self.assertEqual(len(runtime.executions), 1)

    def test_wrong_digest_consumes_token_and_blocks_correct_retry(self):
        prepared = self.prepared()

        wrong = self.gate.confirm(prepared.confirmation_id, "0" * 64)
        self.assertEqual(wrong.status, GATE_STATUS_REJECTED)
        self.assertEqual(wrong.reason, REJECT_CONFIRMATION_DIGEST_MISMATCH)
        self.assertEqual(self.runtime.executions, [])

        retry = self.gate.confirm(prepared.confirmation_id, prepared.plan_digest)
        self.assertEqual(retry.status, GATE_STATUS_REJECTED)
        self.assertEqual(retry.reason, REJECT_CONFIRMATION_NOT_FOUND)
        self.assertEqual(self.runtime.executions, [])
        self.assertIsNone(self.gate.confirmation_store.pending)

    def test_cancel_after_claim_cannot_enable_replay(self):
        prepared = self.prepared()

        confirmed = self.gate.confirm(prepared.confirmation_id, prepared.plan_digest)
        self.assertEqual(confirmed.status, GATE_STATUS_EXECUTED)

        cancelled = self.gate.cancel(prepared.confirmation_id)
        self.assertEqual(cancelled.status, GATE_STATUS_REJECTED)
        self.assertEqual(cancelled.reason, REJECT_CONFIRMATION_NOT_FOUND)

        replay = self.gate.confirm(prepared.confirmation_id, prepared.plan_digest)
        self.assertEqual(replay.status, GATE_STATUS_REJECTED)
        self.assertEqual(len(self.runtime.executions), 1)

    def test_prepare_still_never_executes_under_lock(self):
        result = self.prepared()
        self.assertEqual(result.status, GATE_STATUS_CONFIRMATION_REQUIRED)
        self.assertEqual(self.runtime.executions, [])


class ExecutionGateE2ETests(unittest.TestCase):
    def test_ambiguous_request_stops_before_runtime(self):
        driver = RecordingSimulatedDriver()
        runtime = build_http_runtime(driver, devices=two_room_lamps())
        gate = ExecutionGate(runtime)
        decision = run_decision("Enciende la luz.", runtime)

        self.assertEqual(decision.status, NEEDS_CLARIFICATION)
        result = gate.prepare(decision)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_DECISION_NOT_EXECUTABLE)
        self.assertEqual(driver.apply_calls, 0)

    def test_fabricated_room_request_stops_before_runtime(self):
        driver = RecordingSimulatedDriver()
        runtime = build_http_runtime(driver, devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        decision = run_decision("Enciende la luz del garage.", runtime)

        self.assertEqual(decision.status, NEEDS_CLARIFICATION)
        result = gate.prepare(decision)

        self.assertEqual(result.status, GATE_STATUS_REJECTED)
        self.assertEqual(result.reason, REJECT_DECISION_NOT_EXECUTABLE)
        self.assertEqual(driver.apply_calls, 0)

    def test_full_vertical_requires_confirmation_then_executes(self):
        driver = RecordingSimulatedDriver()
        runtime = build_http_runtime(driver, devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        decision = run_decision("Enciende la luz del cuarto.", runtime)

        self.assertEqual(decision.status, EXECUTABLE_CANDIDATE)
        prepared = gate.prepare(decision)
        self.assertEqual(prepared.status, GATE_STATUS_CONFIRMATION_REQUIRED)
        self.assertEqual(
            runtime.context.device_registry.get("lamp_1").state.properties.get("power"),
            None,
        )
        self.assertEqual(driver.apply_calls, 0)

        confirmed = gate.confirm(prepared.confirmation_id, prepared.plan_digest)
        self.assertEqual(confirmed.status, GATE_STATUS_EXECUTED)
        self.assertEqual(driver.apply_calls, 1)
        self.assertIs(
            runtime.context.device_registry.get("lamp_1").state.properties["power"],
            True,
        )


class ExecutionGateImportBoundaryTests(unittest.TestCase):
    def test_decision_surface_modules_never_import_the_gate_or_runtime(self):
        for path in (
            "jarvis_core/ai/understanding_decision.py",
            "jarvis_core/ai/understanding_resolution.py",
            "jarvis_core/ai/understanding.py",
            "jarvis_core/ai/validation.py",
            "jarvis_core/ai/contracts.py",
            "jarvis_core/ai/confirmation.py",
            "jarvis_core/ai/context.py",
        ):
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            tree = ast.parse(source)
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imports.update(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            )
            forbidden = {
                "jarvis_core.ai.execution_gate",
                "jarvis_core.runtime",
                "jarvis_core.drivers",
                "jarvis_core.http_driver",
                "jarvis_core.mqtt_driver",
                "jarvis_core.api",
                "jarvis_core.dashboard",
            }
            self.assertFalse(
                imports & forbidden,
                f"{path} imports {imports & forbidden}",
            )

    def test_gate_never_imports_providers_or_adapters(self):
        path = "jarvis_core/ai/execution_gate.py"
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        forbidden = {
            "jarvis_core.ai.adapter",
            "jarvis_core.ai.gemini",
            "jarvis_core.ai.ollama",
            "jarvis_core.ai.gemma_android_bridge",
            "jarvis_core.ai.gemma_local",
            "jarvis_core.ai.fake_provider",
            "jarvis_core.drivers",
            "jarvis_core.http_driver",
            "jarvis_core.mqtt_driver",
            "jarvis_core.api",
            "jarvis_core.dashboard",
        }
        self.assertFalse(imports & forbidden, f"{path} imports {imports & forbidden}")


class ExecutionGateCliTests(unittest.TestCase):
    def test_default_tool_run_never_executes(self):
        payload = run_ai_execution_gate("Enciende la luz del cuarto.")

        self.assertEqual(payload["provider"], "demo-understanding-provider")
        self.assertEqual(payload["decision"]["status"], EXECUTABLE_CANDIDATE)
        self.assertIs(payload["decision"]["commands_executed"], False)
        gate = payload["gate"]
        self.assertEqual(gate["status"], GATE_STATUS_CONFIRMATION_REQUIRED)
        self.assertIs(gate["commands_executed"], False)
        self.assertTrue(gate["confirmation_id"])
        self.assertTrue(gate["plan_digest"])
        self.assertIsNone(gate["runtime"])
        self.assertIs(payload["execution"]["runtime"], False)
        self.assertIsNone(payload["device_state"]["power"])

    def test_tool_confirm_flag_turns_lamp_on(self):
        payload = run_ai_execution_gate(
            "Enciende la luz del cuarto.",
            confirm=True,
        )

        gate = payload["gate"]
        self.assertEqual(gate["status"], GATE_STATUS_EXECUTED)
        self.assertIs(gate["commands_executed"], True)
        self.assertEqual(gate["device_id"], "lamp_1")
        self.assertEqual(gate["arguments"], {"state": "true"})
        self.assertTrue(gate["runtime"]["success"])
        self.assertIs(payload["execution"]["runtime"], True)
        self.assertIs(payload["execution"]["hardware"], False)
        self.assertIs(payload["device_state"]["power"], True)

    def test_tool_confirm_flag_turns_lamp_off(self):
        payload = run_ai_execution_gate(
            "Apaga la luz del cuarto.",
            confirm=True,
        )

        gate = payload["gate"]
        self.assertEqual(gate["status"], GATE_STATUS_EXECUTED)
        self.assertIs(gate["commands_executed"], True)
        self.assertEqual(gate["arguments"], {"state": "false"})
        self.assertIs(payload["device_state"]["power"], False)

    def test_tool_reports_blocked_for_unknown_room(self):
        payload = run_ai_execution_gate("Apaga la luz del garage.")

        gate = payload["gate"]
        self.assertEqual(gate["status"], GATE_STATUS_REJECTED)
        self.assertEqual(gate["reason"], REJECT_DECISION_NOT_EXECUTABLE)
        self.assertIs(gate["commands_executed"], False)
        self.assertIsNone(gate["runtime"])
        self.assertIs(payload["execution"]["runtime"], False)

    def test_format_gate_text_payload_renders_confirmation_required(self):
        payload = run_ai_execution_gate("Enciende la luz del cuarto.")
        rendered = format_gate_text_payload(payload)

        self.assertIn("status: confirmation_required", rendered)
        self.assertIn("commands_executed: false", rendered)
        self.assertIn("confirmation_id: ", rendered)
        self.assertIn("plan_digest: ", rendered)
        self.assertIn("lamp_power: none", rendered)

    def test_tool_argument_parser_has_no_bypass_flags(self):
        parser = build_argument_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        for forbidden in (
            "--force",
            "--bypass",
            "--allow-mutation",
            "--allow-unsafe",
            "--no-gate",
        ):
            self.assertNotIn(forbidden, option_strings)
        for required in (
            "--request",
            "--json",
            "--show-canonical",
            "--confirm",
        ):
            self.assertIn(required, option_strings)


def run_decision(request, runtime):
    context = SafeContextBuilder().build(request, runtime.context.device_registry)
    return decide_understanding(
        StaticUnderstandingProvider(room_mutate_proposal(request)),
        context,
        provider_id="gate-test-provider",
        model_id="gate-test",
    )


def room_mutate_proposal(request):
    lowered = request.casefold()
    state = "true" if any(term in lowered for term in ("enciende", "prende")) else "false"
    return {
        "intent": "mutate",
        "referenced_device_text": "luz" if "luz" in lowered else "light",
        "capability_hint": "power.switch",
        "operation_hint": "apply",
        "raw_arguments": [["state", state]],
    }


class StaticUnderstandingProvider:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error

    def extract_understanding(self, context):
        if self.error is not None:
            raise self.error
        return self.output


def executable_decision(
    command,
    *,
    target="lamp_1",
    capability="power.switch",
    confirmation_required=True,
):
    return LocalUnderstandingDecision(
        provider_id="p",
        model_id="m",
        status=EXECUTABLE_CANDIDATE,
        proposal_valid=True,
        resolver_kind=PLAN_KIND_EXECUTE,
        planner_kind=DEVICE_EXECUTE_COMMAND,
        confirmation_required=confirmation_required,
        plan=execute_plan(
            command,
            target=target,
            capability=capability,
            confirmation_required=confirmation_required,
        ),
        commands_executed=False,
    )


def execute_plan(
    command,
    *,
    target="lamp_1",
    capability="power.switch",
    confirmation_required=True,
):
    policy_flags = ("device_mutation",) if not confirmation_required else (
        "device_mutation",
        "requires_confirmation",
    )
    return AIActionPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        kind=PLAN_KIND_EXECUTE,
        steps=(
            AIActionStep(
                index=0,
                canonical_command_text=command,
                safe_description=f"Prepared {capability} on {target}.",
                target_device_id=target,
                capability_name=capability,
                action_kind=ACTION_KIND_MUTATE,
                requires_confirmation=confirmation_required,
                policy_flags=policy_flags,
            ),
        ),
        safe_summary="Prepared a deterministic device plan.",
        confirmation_required=confirmation_required,
        policy_flags=policy_flags,
    )


def clarify_decision():
    return LocalUnderstandingDecision(
        provider_id="p",
        model_id="m",
        status=NEEDS_CLARIFICATION,
        proposal_valid=True,
        resolver_kind=PLAN_KIND_CLARIFY,
        plan=AIActionPlan(
            schema_version=PLAN_SCHEMA_VERSION,
            kind=PLAN_KIND_CLARIFY,
            safe_summary="More information is needed.",
            clarification=AIClarification(
                question="Which device did you mean?",
                reason_code="ambiguous_device",
                missing_fields=("device_id",),
                candidate_options=("lamp_1", "lamp_2"),
            ),
        ),
        commands_executed=False,
    )


def refused_decision():
    return LocalUnderstandingDecision(
        provider_id="p",
        model_id="m",
        status=REFUSED,
        proposal_valid=True,
        resolver_kind=PLAN_KIND_REFUSE,
        plan=AIActionPlan(
            schema_version=PLAN_SCHEMA_VERSION,
            kind=PLAN_KIND_REFUSE,
            safe_summary="The request was refused.",
            refusal=AIRefusal(
                safe_message="That request is not allowed.",
                reason_code="forbidden_operation",
            ),
        ),
        commands_executed=False,
    )


def unavailable_decision():
    return LocalUnderstandingDecision(
        provider_id="p",
        model_id="m",
        status=LOCAL_AI_UNAVAILABLE,
        failure_stage=FAILURE_STAGE_PROVIDER_REQUEST,
        failure_category=AI_PROVIDER_UNAVAILABLE,
        commands_executed=False,
    )


def failed_decision():
    return LocalUnderstandingDecision(
        provider_id="p",
        model_id="m",
        status=UNDERSTANDING_FAILED,
        failure_stage=FAILURE_STAGE_RESOLVER,
        failure_category=AI_RESPONSE_INVALID,
        commands_executed=False,
    )


def room_lamp():
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
            DeviceCapability(
                name="status.read",
                kind="reading",
                parameters={},
            ),
        ],
        metadata={"room": "cuarto"},
    )


def reading_only_lamp():
    return Device(
        id="lamp_1",
        name="Lamp",
        type="light",
        capabilities=[
            DeviceCapability(
                name="status.read",
                kind="reading",
                parameters={},
            ),
        ],
        metadata={"room": "cuarto"},
    )


def two_room_lamps():
    lamp_2 = Device(
        id="lamp_2",
        name="Desk Lamp",
        type="light",
        capabilities=[
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"type": "string", "required": True}},
            ),
        ],
        metadata={"room": "cuarto"},
    )
    return [room_lamp(), lamp_2]


if __name__ == "__main__":
    unittest.main()