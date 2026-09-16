import ast
from dataclasses import FrozenInstanceError
import unittest

from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
    AI_PLAN_REJECTED,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
    PLAN_SCHEMA_VERSION,
    AISafeCapability,
    AISafeContext,
    AISafeDevice,
    AISafeDeviceState,
    AISafePolicyContext,
)
from jarvis_core.ai.gemma_local import GemmaLocalResponse
from jarvis_core.ai.gemma_understanding import (
    GemmaLocalUnderstandingProvider,
    GemmaUnderstandingProviderConfig,
)
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    FAILURE_STAGE_PROPOSAL_NORMALIZATION,
    FAILURE_STAGE_PROVIDER_REQUEST,
    FAILURE_STAGE_RESOLVER,
    LOCAL_AI_UNAVAILABLE,
    NEEDS_CLARIFICATION,
    REFUSED,
    UNDERSTANDING_FAILED,
    LocalUnderstandingDecision,
    decide_understanding,
)
from jarvis_core.ai.understanding_diagnostic import describe_decision
from jarvis_core.planner import DEVICE_EXECUTE_COMMAND
from tools.ai_understanding_decision import (
    build_argument_parser,
    run_ai_understanding_decision,
)


class LocalUnderstandingDecisionTests(unittest.TestCase):
    def test_read_request_is_executable_candidate_without_execution(self):
        decision = decide_understanding(
            StaticUnderstandingProvider(read_proposal()),
            decision_context("Lee status.read del dispositivo lamp_1."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
            clock=FakeClock([1.0, 1.010]),
        )

        self.assertEqual(decision.status, EXECUTABLE_CANDIDATE)
        self.assertTrue(decision.proposal_valid)
        self.assertEqual(decision.resolver_kind, PLAN_KIND_EXECUTE)
        self.assertEqual(decision.planner_kind, DEVICE_EXECUTE_COMMAND)
        self.assertFalse(decision.confirmation_required)
        self.assertIsNone(decision.failure_stage)
        self.assertIsNone(decision.failure_category)
        self.assertEqual(decision.latency_ms, 10)
        self.assertIs(decision.commands_executed, False)
        self.assertEqual(
            decision.plan.steps[0].canonical_command_text,
            "device read lamp_1 status.read",
        )

    def test_mutation_is_executable_candidate_and_requires_confirmation(self):
        decision = decide_understanding(
            StaticUnderstandingProvider(mutate_proposal()),
            decision_context(
                "Enciende power.switch del dispositivo lamp_1 con state true."
            ),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
            clock=FakeClock([1.0, 1.010]),
        )

        self.assertEqual(decision.status, EXECUTABLE_CANDIDATE)
        self.assertTrue(decision.confirmation_required)
        self.assertEqual(decision.plan.steps[0].action_kind, ACTION_KIND_MUTATE)
        self.assertEqual(
            decision.plan.steps[0].canonical_command_text,
            "device apply lamp_1 power.switch state=true",
        )
        self.assertIs(decision.commands_executed, False)

    def test_ambiguous_request_never_executes(self):
        decision = decide_understanding(
            StaticUnderstandingProvider(ambiguous_proposal()),
            decision_context("Enciende la luz.", include_second_lamp=True),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        self.assertEqual(decision.status, NEEDS_CLARIFICATION)
        self.assertEqual(decision.resolver_kind, PLAN_KIND_CLARIFY)
        self.assertIsNone(decision.planner_kind)
        self.assertEqual(decision.plan.steps, ())
        self.assertEqual(decision.plan.clarification.reason_code, "ambiguous_device")
        self.assertIs(decision.commands_executed, False)

    def test_fabricated_device_never_executes(self):
        decision = decide_understanding(
            StaticUnderstandingProvider(fabricated_device_proposal()),
            decision_context("Lee el estado de lamp_99."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        self.assertEqual(decision.status, NEEDS_CLARIFICATION)
        self.assertEqual(decision.plan.steps, ())
        self.assertEqual(
            decision.plan.clarification.reason_code,
            "insufficient_context",
        )
        self.assertIs(decision.commands_executed, False)

    def test_missing_required_argument_fails_closed_or_clarifies(self):
        for proposal in (missing_argument_proposal(),):
            with self.subTest(proposal=proposal):
                decision = decide_understanding(
                    StaticUnderstandingProvider(proposal),
                    decision_context("Cambia power.switch del dispositivo lamp_1."),
                    provider_id="gemma-local-understanding",
                    model_id="gemma-test",
                )

                self.assertEqual(decision.status, NEEDS_CLARIFICATION)
                self.assertEqual(decision.plan.steps, ())
                self.assertEqual(
                    decision.plan.clarification.reason_code,
                    "missing_parameter",
                )

    def test_destructive_request_refuses_even_when_provider_fails(self):
        contexts = [
            decision_context("Borra todos los dispositivos."),
            decision_context("Borra todos los dispositivos."),
            decision_context("Borra todos los dispositivos."),
        ]
        providers = [
            StaticUnderstandingProvider(read_proposal()),
            StaticUnderstandingProvider({"kind": "execute", "steps": []}),
            StaticUnderstandingProvider(error=RuntimeError("provider crashed")),
        ]
        for index, provider in enumerate(providers):
            with self.subTest(index=index):
                decision = decide_understanding(
                    provider,
                    contexts[index],
                    provider_id="gemma-local-understanding",
                    model_id="gemma-test",
                )

                self.assertEqual(decision.status, REFUSED)
                self.assertEqual(decision.resolver_kind, PLAN_KIND_REFUSE)
                self.assertIsNone(decision.planner_kind)
                self.assertEqual(decision.plan.kind, PLAN_KIND_REFUSE)
                self.assertEqual(
                    decision.plan.refusal.reason_code,
                    "forbidden_operation",
                )
                self.assertEqual(decision.plan.steps, ())
                self.assertIs(decision.commands_executed, False)

    def test_invalid_capability_fails_closed(self):
        decision = decide_understanding(
            StaticUnderstandingProvider(invalid_capability_proposal()),
            decision_context("Lee battery.level del dispositivo lamp_1."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        self.assertEqual(decision.status, NEEDS_CLARIFICATION)
        self.assertEqual(decision.plan.steps, ())
        self.assertEqual(
            decision.plan.clarification.reason_code,
            "unsupported_request",
        )

    def test_provider_timeout_is_understanding_failed(self):
        provider = provider_with(StubGemmaUnderstandingTransport(error=TimeoutError()))
        decision = decide_understanding(
            provider,
            decision_context("Lee status.read del dispositivo lamp_1."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        self.assertEqual(decision.status, UNDERSTANDING_FAILED)
        self.assertEqual(decision.failure_stage, FAILURE_STAGE_PROVIDER_REQUEST)
        self.assertEqual(decision.failure_category, AI_PROVIDER_TIMEOUT)
        self.assertIsNone(decision.plan)
        self.assertIs(decision.commands_executed, False)

    def test_bridge_unavailable_is_local_ai_unavailable(self):
        provider = provider_with(
            StubGemmaUnderstandingTransport(error=OSError("connection refused"))
        )
        decision = decide_understanding(
            provider,
            decision_context("Lee status.read del dispositivo lamp_1."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        self.assertEqual(decision.status, LOCAL_AI_UNAVAILABLE)
        self.assertFalse(decision.proposal_valid)
        self.assertIsNone(decision.plan)
        self.assertIsNone(decision.resolver_kind)
        self.assertEqual(decision.failure_stage, FAILURE_STAGE_PROVIDER_REQUEST)
        self.assertEqual(decision.failure_category, AI_PROVIDER_UNAVAILABLE)
        self.assertIs(decision.commands_executed, False)

    def test_malformed_response_is_understanding_failed(self):
        decision = decide_understanding(
            StaticUnderstandingProvider({"kind": "execute", "steps": []}),
            decision_context("Lee status.read del dispositivo lamp_1."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        self.assertEqual(decision.status, UNDERSTANDING_FAILED)
        self.assertEqual(
            decision.failure_stage,
            FAILURE_STAGE_PROPOSAL_NORMALIZATION,
        )
        self.assertEqual(decision.failure_category, AI_RESPONSE_INVALID)
        self.assertIsNone(decision.plan)

    def test_unknown_proposal_fields_fail_closed(self):
        decision = decide_understanding(
            StaticUnderstandingProvider({"intent": "read", "extra": "nope"}),
            decision_context("Lee status.read del dispositivo lamp_1."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        self.assertEqual(decision.status, UNDERSTANDING_FAILED)
        self.assertEqual(
            decision.failure_stage,
            FAILURE_STAGE_PROPOSAL_NORMALIZATION,
        )
        self.assertEqual(decision.failure_category, AI_RESPONSE_INVALID)

    def test_planner_rejection_blocks_executable_candidate(self):
        context = decision_context(
            "Lee bad;capability de lamp_1.",
            capabilities=(
                AISafeCapability(name="bad;capability", kind="reading", parameters=()),
            ),
        )
        decision = decide_understanding(
            StaticUnderstandingProvider(
                {
                    "intent": "read",
                    "referenced_device_id": "lamp_1",
                    "capability_hint": "bad;capability",
                    "operation_hint": "read",
                }
            ),
            context,
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        self.assertEqual(decision.status, UNDERSTANDING_FAILED)
        self.assertEqual(decision.failure_stage, FAILURE_STAGE_RESOLVER)
        self.assertEqual(decision.failure_category, AI_PLAN_REJECTED)
        self.assertIsNone(decision.plan)
        self.assertIs(decision.commands_executed, False)

    def test_decision_is_immutable_and_cannot_claim_execution(self):
        decision = decide_understanding(
            StaticUnderstandingProvider(read_proposal()),
            decision_context("Lee status.read del dispositivo lamp_1."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        with self.assertRaises(FrozenInstanceError):
            decision.status = REFUSED
        with self.assertRaises(ValueError):
            LocalUnderstandingDecision(
                provider_id="zero",
                model_id="zero",
                status=REFUSED,
                plan=build_default_refuse_plan(),
                commands_executed=True,
            )

    def test_describe_decision_hides_canonical_by_default(self):
        decision = decide_understanding(
            StaticUnderstandingProvider(read_proposal()),
            decision_context("Lee status.read del dispositivo lamp_1."),
            provider_id="gemma-local-understanding",
            model_id="gemma-test",
        )

        payload = describe_decision(decision)
        self.assertNotIn("canonical_command_text", payload)
        self.assertIs(payload["commands_executed"], False)
        shown = describe_decision(decision, show_canonical=True)
        self.assertEqual(
            shown["canonical_command_text"],
            "device read lamp_1 status.read",
        )


class LocalUnderstandingDecisionImportBoundaryTests(unittest.TestCase):
    def test_decision_diagnostic_and_tool_do_not_import_execution_boundaries(self):
        for path in (
            "jarvis_core/ai/understanding_decision.py",
            "jarvis_core/ai/understanding_diagnostic.py",
            "tools/ai_understanding_decision.py",
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
                "jarvis_core.runtime",
                "jarvis_core.drivers",
                "jarvis_core.http_driver",
                "jarvis_core.mqtt_driver",
                "jarvis_core.voice",
                "jarvis_core.api",
                "jarvis_core.dashboard",
                "jarvis_core.ai.adapter",
                "jarvis_core.ai.gemini",
                "jarvis_core.ai.ollama",
                "jarvis_core.remote",
            }
            self.assertFalse(imports & forbidden, f"{path} imports {imports & forbidden}")
            self.assertNotIn("handle_adapter_input", source)
            self.assertNotIn("FakeAIAdapter", source)


class LocalUnderstandingDecisionCliTests(unittest.TestCase):
    def test_cli_reports_commands_executed_false_and_execution_disconnected(self):
        transport = StubGemmaUnderstandingTransport(read_proposal())
        payload = run_ai_understanding_decision(
            "Lee status.read del dispositivo lamp_1.",
            model="gemma-test",
            transport=transport,
            clock=FakeClock([1.0, 1.010]),
        )

        self.assertEqual(payload["provider"], "gemma-local-understanding")
        self.assertEqual(payload["model"], "gemma-test")
        for key in (
            "runtime",
            "drivers",
            "stt",
            "voice",
            "action_execution",
            "cloud_fallback",
            "model_router",
        ):
            self.assertIs(payload["execution"][key], False)
        decision = payload["decision"]
        self.assertEqual(decision["status"], EXECUTABLE_CANDIDATE)
        self.assertIs(decision["commands_executed"], False)
        self.assertEqual(decision["latency_ms"], 10)
        self.assertNotIn("canonical_command_text", decision)

    def test_cli_canonical_is_opt_in_and_shown_explicitly(self):
        transport = StubGemmaUnderstandingTransport(read_proposal())
        payload = run_ai_understanding_decision(
            "Lee status.read del dispositivo lamp_1.",
            model="gemma-test",
            transport=transport,
            clock=FakeClock([1.0, 1.010]),
            show_canonical=True,
        )

        self.assertEqual(
            payload["decision"]["canonical_command_text"],
            "device read lamp_1 status.read",
        )

    def test_cli_flags_do_not_include_execution_flags(self):
        parser = build_argument_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        for forbidden in (
            "--execute",
            "--apply",
            "--runtime",
            "--driver",
            "--confirm",
            "--cloud-fallback",
        ):
            self.assertNotIn(forbidden, option_strings)
        for required in (
            "--request",
            "--model",
            "--host",
            "--port",
            "--json",
            "--show-canonical",
        ):
            self.assertIn(required, option_strings)


def read_proposal():
    return {
        "intent": "read",
        "referenced_device_id": "lamp_1",
        "capability_hint": "status.read",
        "operation_hint": "read",
    }


def mutate_proposal():
    return {
        "intent": "mutate",
        "referenced_device_id": "lamp_1",
        "capability_hint": "power.switch",
        "operation_hint": "apply",
        "raw_arguments": [["state", "true"]],
    }


def ambiguous_proposal():
    return {
        "intent": "mutate",
        "referenced_device_text": "light",
        "capability_hint": "power.switch",
        "operation_hint": "apply",
        "raw_arguments": [["state", "true"]],
    }


def fabricated_device_proposal():
    return {
        "intent": "read",
        "referenced_device_id": "lamp_99",
        "capability_hint": "status.read",
        "operation_hint": "read",
    }


def missing_argument_proposal():
    return {
        "intent": "mutate",
        "referenced_device_id": "lamp_1",
        "capability_hint": "power.switch",
        "operation_hint": "apply",
    }


def invalid_capability_proposal():
    return {
        "intent": "read",
        "referenced_device_id": "lamp_1",
        "capability_hint": "battery.level",
        "operation_hint": "read",
    }


def provider_with(transport, *, model="gemma-test"):
    return GemmaLocalUnderstandingProvider(
        GemmaUnderstandingProviderConfig(model),
        transport=transport,
    )


def decision_context(
    user_request,
    *,
    include_second_lamp=False,
    capabilities=None,
):
    devices = [
        safe_lamp(
            "lamp_1",
            "Lamp",
            "light",
            capabilities=capabilities or default_capabilities(),
        )
    ]
    if include_second_lamp:
        devices.append(safe_lamp("lamp_2", "Desk Lamp", "light", capabilities=default_capabilities()))
    return AISafeContext(
        schema_version=PLAN_SCHEMA_VERSION,
        user_request=user_request,
        devices=tuple(devices),
        command_grammar=(),
        policies=AISafePolicyContext(
            max_plan_steps=5,
            confirmation_required_for_mutations=True,
        ),
    )


def safe_lamp(device_id, display_name, device_type, *, capabilities):
    return AISafeDevice(
        device_id=device_id,
        display_name=display_name,
        device_type=device_type,
        capabilities=tuple(capabilities),
        state=AISafeDeviceState("known", (("power", False),), None),
    )


def default_capabilities():
    return (
        AISafeCapability(name="status.read", kind="reading", parameters=()),
        AISafeCapability(
            name="power.switch",
            kind="action",
            parameters=(
                (
                    ("name", "state"),
                    ("type", "string"),
                    ("required", True),
                ),
            ),
        ),
    )


def build_default_refuse_plan():
    from jarvis_core.ai.validation import normalize_plan, validate_plan_shape

    return validate_plan_shape(
        normalize_plan(
            {
                "schema_version": 1,
                "kind": "refuse",
                "steps": [],
                "safe_summary": "The request was refused.",
                "clarification": None,
                "refusal": {
                    "safe_message": "That request is not allowed.",
                    "reason_code": "forbidden_operation",
                },
                "confirmation_required": False,
                "policy_flags": [],
            }
        )
    )


class StaticUnderstandingProvider:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error

    def extract_understanding(self, context):
        if self.error is not None:
            raise self.error
        return self.output


class StubGemmaUnderstandingTransport:
    def __init__(self, body=None, *, error=None):
        self.body = body
        self.error = error
        self.requests = []

    def generate(self, request, timeout_seconds, max_response_bytes):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return GemmaLocalResponse(self.body)


class FakeClock:
    def __init__(self, values):
        self.values = list(values)

    def __call__(self):
        if not self.values:
            raise AssertionError("FakeClock exhausted")
        return self.values.pop(0)


if __name__ == "__main__":
    unittest.main()