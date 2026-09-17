"""Focused tests for the safe local understanding execution gate.

These tests prove the thesis execution vertical invariants:

- Only validated single-step ``power.switch`` execute candidates reach Runtime.
- Every rejected path stops before Runtime (never constructs or forwards a
  command).
- ``commands_executed`` on the decision surface stays honest and false.
- The decision/provider/validation modules never import the gate or execution
  boundaries (AST-level boundary enforcement).
- The gate forwards commands to the existing Runtime and surfaces device-level
  success or failure instead of hiding it.
"""

import ast
from dataclasses import FrozenInstanceError
import unittest

from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
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
    ALLOWED_POWER_SWITCH_STATES,
    EXECUTION_GATE_SOURCE,
    REJECT_DECISION_NOT_EXECUTABLE,
    REJECT_INVALID_ARGUMENTS,
    REJECT_INVALID_COMMAND,
    REJECT_MULTI_STEP_PLAN,
    REJECT_UNSUPPORTED_CAPABILITY,
    REJECT_UNSUPPORTED_DECISION,
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
from jarvis_core.devices import Device, DeviceCapability
from jarvis_core.domain import CapabilityResult
from jarvis_core.drivers import DriverResult, SimulatedDriver
from jarvis_core.planner import (
    APPLY_OPERATION,
    DEVICE_EXECUTE_COMMAND,
    DEVICE_CATALOG_COMMAND,
    Planner,
)
from tools.ai_execution_gate import (
    build_argument_parser,
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
    def __init__(self, result=None):
        self.executions = []
        self.result = result or CapabilityResult(
            success=True,
            message="ok",
            data={"device_id": "lamp_1", "capability": "power.switch", "operation": "apply"},
        )

    def execute(self, command, correlation_id=None):
        self.executions.append(command)
        return self.result


class ExecutionGateCoreTests(unittest.TestCase):
    def test_executable_candidate_reaches_runtime_with_exact_command(self):
        runtime = RecordingRuntime()
        gate = ExecutionGate(runtime)

        result = gate.execute(executable_decision("device apply lamp_1 power.switch state=true"))

        self.assertTrue(result.executed)
        self.assertEqual(result.device_id, "lamp_1")
        self.assertEqual(result.capability, "power.switch")
        self.assertEqual(result.arguments, {"state": "true"})
        self.assertIsNone(result.reason)
        self.assertEqual(len(runtime.executions), 1)
        command = runtime.executions[0]
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

    def test_power_switch_on_and_off_reach_runtime(self):
        for raw_state in ("true", "false", "on", "off"):
            with self.subTest(state=raw_state):
                runtime = RecordingRuntime()
                gate = ExecutionGate(runtime)
                result = gate.execute(
                    executable_decision(
                        f"device apply lamp_1 power.switch state={raw_state}"
                    )
                )
                self.assertTrue(result.executed)
                self.assertEqual(result.arguments, {"state": raw_state})
                self.assertEqual(len(runtime.executions), 1)

    def test_allowed_state_values_are_explicit(self):
        self.assertEqual(
            ALLOWED_POWER_SWITCH_STATES,
            frozenset({"true", "false", "on", "off"}),
        )

    def test_result_invariants_and_immutability(self):
        runtime = RecordingRuntime()
        result = ExecutionGate(runtime).execute(
            executable_decision("device apply lamp_1 power.switch state=true")
        )
        with self.assertRaises(FrozenInstanceError):
            result.executed = False
        self.assertIsInstance(result.runtime_result, CapabilityResult)
        with self.assertRaises(ValueError):
            ExecutionGateResult(executed=True, runtime_result=None)
        with self.assertRaises(ValueError):
            ExecutionGateResult(executed=False, reason="nope")
        with self.assertRaises(ValueError):
            ExecutionGateResult(executed=True, runtime_result=CapabilityResult(True, "ok"), reason=REJECT_MULTI_STEP_PLAN)

    def test_runtime_failure_is_surfaced_not_hidden(self):
        driver = FailingApplyDriver()
        runtime = build_http_runtime(driver, devices=[room_lamp()])
        gate = ExecutionGate(runtime)

        result = gate.execute(executable_decision("device apply lamp_1 power.switch state=true"))

        self.assertTrue(result.executed)
        self.assertEqual(driver.apply_calls, 1)
        self.assertFalse(result.runtime_result.success)
        self.assertEqual(result.runtime_result.error, "device_execution_failed")
        self.assertIsNone(result.reason)

    def test_grid_pass_through_real_runtime_updates_device_state(self):
        driver = RecordingSimulatedDriver()
        runtime = build_http_runtime(driver, devices=[room_lamp()])
        gate = ExecutionGate(runtime)

        result = gate.execute(executable_decision("device apply lamp_1 power.switch state=true"))

        self.assertTrue(result.executed)
        self.assertTrue(result.runtime_result.success)
        self.assertEqual(driver.apply_calls, 1)
        self.assertIs(runtime.context.device_registry.get("lamp_1").state.properties["power"], True)

    def test_gate_and_gate_input_rejections_are_structurally_rejected(self):
        with self.assertRaises(TypeError):
            ExecutionGate(object())

    def test_executable_candidate_requires_execute_plan_shape(self):
        with self.assertRaises(ValueError):
            LocalUnderstandingDecision(
                provider_id="p",
                model_id="m",
                status=EXECUTABLE_CANDIDATE,
                planner_kind=DEVICE_EXECUTE_COMMAND,
                commands_executed=False,
            )

    def test_decision_surface_never_claims_execution(self):
        with self.assertRaises(ValueError):
            LocalUnderstandingDecision(
                provider_id="p",
                model_id="m",
                status=EXECUTABLE_CANDIDATE,
                resolver_kind=PLAN_KIND_EXECUTE,
                planner_kind=DEVICE_EXECUTE_COMMAND,
                plan=execute_plan("device apply lamp_1 power.switch state=true"),
                commands_executed=True,
            )


class ExecutionGateRejectedPathTests(unittest.TestCase):
    def setUp(self):
        self.runtime = RecordingRuntime()

    def assert_rejected(self, decision, expected_reason):
        result = ExecutionGate(self.runtime).execute(decision)
        self.assertFalse(result.executed)
        self.assertEqual(result.reason, expected_reason)
        self.assertIsNone(result.runtime_result)
        self.assertEqual(self.runtime.executions, [], "rejected decisions must not reach Runtime")

    def test_needs_clarification_never_reaches_runtime(self):
        self.assert_rejected(clarify_decision(), REJECT_DECISION_NOT_EXECUTABLE)

    def test_refused_never_reaches_runtime(self):
        self.assert_rejected(refused_decision(), REJECT_DECISION_NOT_EXECUTABLE)

    def test_local_ai_unavailable_never_reaches_runtime(self):
        self.assert_rejected(unavailable_decision(), REJECT_DECISION_NOT_EXECUTABLE)

    def test_understanding_failed_never_reaches_runtime(self):
        self.assert_rejected(failed_decision(), REJECT_DECISION_NOT_EXECUTABLE)

    def test_non_decision_input_never_reaches_runtime(self):
        self.assert_rejected({"status": EXECUTABLE_CANDIDATE}, REJECT_UNSUPPORTED_DECISION)
        self.assert_rejected(None, REJECT_UNSUPPORTED_DECISION)

    def test_multi_step_plan_never_reaches_runtime(self):
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
        self.assert_rejected(decision, REJECT_MULTI_STEP_PLAN)

    def test_planner_unknown_command_never_reaches_runtime(self):
        decision = executable_decision("hello there")
        self.assert_rejected(decision, REJECT_INVALID_COMMAND)

    def test_non_execute_command_never_reaches_runtime(self):
        decision = executable_decision("time now")
        self.assert_rejected(decision, REJECT_INVALID_COMMAND)

    def test_unsafe_shell_command_never_reaches_runtime(self):
        decision = executable_decision("device apply lamp_1 power.switch state=true; rm -rf")
        self.assert_rejected(decision, REJECT_INVALID_COMMAND)

    def test_newline_injection_never_reaches_runtime(self):
        decision = executable_decision("device apply lamp_1 power.switch state=true\ndevice list")
        self.assert_rejected(decision, REJECT_INVALID_COMMAND)

    def test_unsupported_capability_never_reaches_runtime(self):
        decision = executable_decision(
            "device apply lamp_1 status.read state=true",
            target="lamp_1",
            capability="status.read",
        )
        self.assert_rejected(decision, REJECT_UNSUPPORTED_CAPABILITY)

    def test_misleading_step_capability_never_reaches_runtime(self):
        decision = executable_decision(
            "device apply lamp_1 power.switch state=true",
            target="lamp_1",
            capability="status.read",
        )
        self.assert_rejected(decision, REJECT_INVALID_COMMAND)

    def test_misleading_step_device_never_reaches_runtime(self):
        decision = executable_decision(
            "device apply lamp_2 power.switch state=true",
            target="lamp_1",
            capability="power.switch",
        )
        self.assert_rejected(decision, REJECT_INVALID_COMMAND)

    def test_missing_parameter_never_reaches_runtime(self):
        decision = executable_decision("device apply lamp_1 power.switch")
        self.assert_rejected(decision, REJECT_INVALID_ARGUMENTS)

    def test_unknown_parameter_value_never_reaches_runtime(self):
        decision = executable_decision("device apply lamp_1 power.switch state=maybe")
        self.assert_rejected(decision, REJECT_INVALID_ARGUMENTS)

    def test_extra_parameter_never_reaches_runtime(self):
        decision = executable_decision(
            "device apply lamp_1 power.switch state=true brightness=5"
        )
        self.assert_rejected(decision, REJECT_INVALID_ARGUMENTS)

    def test_wrong_parameter_key_never_reaches_runtime(self):
        decision = executable_decision("device apply lamp_1 power.switch brightness=5")
        self.assert_rejected(decision, REJECT_INVALID_ARGUMENTS)

    def test_read_operation_is_not_gated_in_v1(self):
        decision = executable_decision(
            "device read lamp_1 status.read",
            target="lamp_1",
            capability="status.read",
        )
        self.assert_rejected(decision, REJECT_UNSUPPORTED_CAPABILITY)


class ExecutionGateE2ETests(unittest.TestCase):
    def test_spanish_on_light_in_room_executes_and_turns_on(self):
        runtime = build_http_runtime(RecordingSimulatedDriver(), devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        decision = run_decision("Enciende la luz del cuarto.", runtime)

        result = gate.execute(decision)

        self.assertTrue(result.executed)
        self.assertEqual(decision.status, EXECUTABLE_CANDIDATE)
        self.assertEqual(result.device_id, "lamp_1")
        self.assertEqual(result.arguments, {"state": "true"})
        self.assertTrue(result.runtime_result.success)
        self.assertIs(runtime.context.device_registry.get("lamp_1").state.properties["power"], True)
        self.assertIs(decision.commands_executed, False)

    def test_spanish_off_light_in_room_executes_and_turns_off(self):
        runtime = build_http_runtime(RecordingSimulatedDriver(), devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        decision = run_decision("Apaga la luz del cuarto.", runtime)

        result = gate.execute(decision)

        self.assertTrue(result.executed)
        self.assertEqual(result.arguments, {"state": "false"})
        self.assertTrue(result.runtime_result.success)
        self.assertIs(runtime.context.device_registry.get("lamp_1").state.properties["power"], False)
        self.assertIs(decision.commands_executed, False)

    def test_e2e_uses_existing_planner_and_mutation_result(self):
        runtime = build_http_runtime(RecordingSimulatedDriver(), devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        decision = run_decision("Enciende la luz del cuarto.", runtime)

        result = gate.execute(decision)

        self.assertEqual(result.runtime_result.data["operation"], APPLY_OPERATION)
        self.assertEqual(result.runtime_result.data["capability"], "power.switch")

    def test_ambiguous_request_stops_before_runtime(self):
        driver = RecordingSimulatedDriver()
        runtime = build_http_runtime(driver, devices=two_room_lamps())
        gate = ExecutionGate(runtime)
        decision = run_decision("Enciende la luz.", runtime)

        self.assertEqual(decision.status, NEEDS_CLARIFICATION)
        result = gate.execute(decision)

        self.assertFalse(result.executed)
        self.assertEqual(result.reason, REJECT_DECISION_NOT_EXECUTABLE)
        self.assertEqual(driver.apply_calls, 0)

    def test_fabricated_device_request_stops_before_runtime(self):
        driver = RecordingSimulatedDriver()
        runtime = build_http_runtime(driver, devices=[room_lamp()])
        gate = ExecutionGate(runtime)
        decision = run_decision("Enciende la luz del garage.", runtime)

        self.assertEqual(decision.status, NEEDS_CLARIFICATION)
        result = gate.execute(decision)

        self.assertFalse(result.executed)
        self.assertEqual(result.reason, REJECT_DECISION_NOT_EXECUTABLE)
        self.assertEqual(driver.apply_calls, 0)


class ExecutionGateImportBoundaryTests(unittest.TestCase):
    def test_decision_surface_modules_never_import_the_gate_or_runtime(self):
        for path in (
            "jarvis_core/ai/understanding_decision.py",
            "jarvis_core/ai/understanding_resolution.py",
            "jarvis_core/ai/understanding.py",
            "jarvis_core/ai/validation.py",
            "jarvis_core/ai/contracts.py",
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
    def test_tool_reports_executed_on_room_light(self):
        payload = run_ai_execution_gate("Enciende la luz del cuarto.")

        self.assertEqual(payload["provider"], "demo-understanding-provider")
        self.assertEqual(payload["decision"]["status"], EXECUTABLE_CANDIDATE)
        self.assertIs(payload["decision"]["commands_executed"], False)
        gate = payload["gate"]
        self.assertTrue(gate["executed"])
        self.assertEqual(gate["device_id"], "lamp_1")
        self.assertEqual(gate["arguments"], {"state": "true"})
        self.assertIsNone(gate["reason"])
        self.assertTrue(gate["runtime"]["success"])
        self.assertIs(payload["execution"]["hardware"], False)

    def test_tool_reports_blocked_for_unknown_room(self):
        payload = run_ai_execution_gate("Apaga la luz del garage.")

        gate = payload["gate"]
        self.assertFalse(gate["executed"])
        self.assertEqual(gate["reason"], REJECT_DECISION_NOT_EXECUTABLE)
        self.assertIsNone(gate["runtime"])

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
            "--confirm",
            "--allow-mutation",
            "--allow-unsafe",
            "--no-gate",
        ):
            self.assertNotIn(forbidden, option_strings)
        for required in (
            "--request",
            "--json",
            "--show-canonical",
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


def executable_decision(command, *, target="lamp_1", capability="power.switch"):
    return LocalUnderstandingDecision(
        provider_id="p",
        model_id="m",
        status=EXECUTABLE_CANDIDATE,
        proposal_valid=True,
        resolver_kind=PLAN_KIND_EXECUTE,
        planner_kind=DEVICE_EXECUTE_COMMAND,
        confirmation_required=True,
        plan=execute_plan(command, target=target, capability=capability),
        commands_executed=False,
    )


def execute_plan(command, *, target="lamp_1", capability="power.switch"):
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
                requires_confirmation=True,
                policy_flags=("device_mutation", "requires_confirmation"),
            ),
        ),
        safe_summary="Prepared a deterministic device plan.",
        confirmation_required=True,
        policy_flags=("device_mutation", "requires_confirmation"),
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