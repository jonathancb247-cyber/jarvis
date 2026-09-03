import ast
import json
from pathlib import Path
import unittest

from jarvis_core.ai.contracts import (
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
)
from jarvis_core.ai.context import SafeContextBuilder
from jarvis_core.ai.gemma_local import (
    GemmaLocalAIProvider,
    GemmaLocalProviderConfig,
    GemmaLocalProviderError,
    GemmaLocalResponse,
    UnconfiguredGemmaLocalTransport,
    _system_instruction,
)
from jarvis_core.ai.structured_bakeoff import (
    StructuredProviderBakeOff,
    build_default_structured_ai_fixtures,
)
from tests.test_ai_adapter import test_runtime


class GemmaLocalConfigTests(unittest.TestCase):
    def test_config_requires_bounded_model_and_limits(self):
        config = GemmaLocalProviderConfig("gemma-4-e2b")

        self.assertEqual(config.model, "gemma-4-e2b")
        self.assertEqual(config.timeout_seconds, 60)
        self.assertEqual(config.maximum_output_tokens, 512)
        with self.assertRaises(ValueError):
            GemmaLocalProviderConfig("")
        with self.assertRaises(ValueError):
            GemmaLocalProviderConfig("bad\nmodel")
        with self.assertRaises(ValueError):
            GemmaLocalProviderConfig("gemma", timeout_seconds=0)
        with self.assertRaises(ValueError):
            GemmaLocalProviderConfig("gemma", maximum_response_bytes=10)

    def test_default_transport_is_explicitly_unavailable(self):
        provider = GemmaLocalAIProvider(GemmaLocalProviderConfig("gemma-4-e2b"))

        with self.assertRaises(GemmaLocalProviderError) as raised:
            provider.generate_plan(safe_context("Lee status.read del dispositivo lamp_1."))

        self.assertEqual(raised.exception.code, AI_PROVIDER_UNAVAILABLE)


class GemmaLocalProviderTests(unittest.TestCase):
    def test_provider_builds_structured_request_without_real_transport_assumptions(self):
        transport = FakeGemmaTransport(success_plan())
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=transport,
        )

        payload = provider.generate_plan(safe_context("Read status.read from lamp_1."))
        request = transport.calls[0]["request"]

        self.assertEqual(payload["kind"], "execute")
        self.assertEqual(request["provider"], "gemma-local")
        self.assertEqual(request["model"], "gemma-4-e2b")
        self.assertEqual(request["response_format"]["schema"]["type"], "object")
        self.assertEqual(request["generation_config"]["temperature"], 0)
        self.assertEqual(request["generation_config"]["max_output_tokens"], 512)
        self.assertFalse(request["execution"]["runtime"])
        self.assertFalse(request["execution"]["drivers"])
        self.assertFalse(request["execution"]["tools"])
        self.assertNotIn("adb", json.dumps(request).lower())
        self.assertNotIn("http://", json.dumps(request).lower())
        self.assertNotIn("socket", json.dumps(request).lower())

    def test_system_instruction_preserves_boundary_and_shape_rules(self):
        instruction = _system_instruction()

        self.assertIn("Return only JSON", instruction)
        self.assertIn("AIActionPlan schema", instruction)
        self.assertIn("JarvisOS English command grammar", instruction)
        self.assertIn("Do not invent devices or capabilities", instruction)
        self.assertIn("If kind is execute", instruction)
        self.assertIn("steps must contain 1..5 executable steps", instruction)
        self.assertIn("If kind is clarify", instruction)
        self.assertIn("steps must be []", instruction)
        self.assertIn("If kind is refuse", instruction)
        self.assertIn("never call tools", instruction)
        self.assertIn("Do not include chain-of-thought", instruction)

    def test_valid_execute_clarify_refuse_and_spanish_plans_are_returned_raw(self):
        cases = [
            ("Lee status.read del dispositivo lamp_1.", success_plan()),
            ("Enciende la luz.", clarify_plan()),
            ("Borra todos los dispositivos.", refusal_plan()),
        ]
        for request, plan in cases:
            with self.subTest(request=request):
                provider = GemmaLocalAIProvider(
                    GemmaLocalProviderConfig("gemma-4-e2b"),
                    transport=FakeGemmaTransport(plan),
                )

                payload = provider.generate_plan(safe_context(request))

                self.assertEqual(payload["kind"], plan["kind"])

    def test_relative_time_shape_is_left_for_existing_bakeoff_validation(self):
        fixture = _fixture("relative_time_two_minutes")
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=FakeGemmaTransport(
                success_plan(
                    "device read lamp_1 status.read schedule_at=2026-09-01T12:02:00Z"
                )
            ),
        )

        result = StructuredProviderBakeOff(
            provider,
            provider_name="gemma-local",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(result.metrics.ai_action_plan_valid, 1.0)
        self.assertEqual(result.metrics.relative_time_reasoning, 1.0)
        self.assertEqual(result.arguments["schedule_at"], "2026-09-01T12:02:00Z")

    def test_schema_invalid_plan_is_left_for_existing_bakeoff_validation(self):
        fixture = _fixture("spanish_simple_read")
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=FakeGemmaTransport({"schema_version": 1, "kind": "execute"}),
        )

        result = StructuredProviderBakeOff(
            provider,
            provider_name="gemma-local",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(result.normalized_failure, AI_RESPONSE_INVALID)
        self.assertEqual(result.metrics.ai_action_plan_valid, 0.0)

    def test_native_tool_call_is_mapped_to_raw_plan_without_execution(self):
        transport = FakeGemmaTransport(
            {
                "tool_calls": [
                    {
                        "function": {
                            "name": "ai_action_plan",
                            "arguments": success_plan(),
                        }
                    }
                ]
            }
        )
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("function-gemma-270m"),
            transport=transport,
        )

        payload = provider.generate_plan(safe_context("Read status.read from lamp_1."))

        self.assertEqual(payload["kind"], "execute")
        self.assertEqual(len(transport.calls), 1)

    def test_text_json_envelopes_are_supported_but_extra_text_is_rejected(self):
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=FakeGemmaTransport({"output_text": "\n" + json.dumps(success_plan()) + "\n"}),
        )
        extra = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=FakeGemmaTransport({"output_text": "Here is JSON " + json.dumps(success_plan())}),
        )

        self.assertEqual(
            provider.generate_plan(safe_context("Read status.read from lamp_1."))["kind"],
            "execute",
        )
        with self.assertRaises(GemmaLocalProviderError) as raised:
            extra.generate_plan(safe_context("Read status.read from lamp_1."))
        self.assertEqual(raised.exception.code, AI_RESPONSE_INVALID)

    def test_multiple_json_objects_are_rejected(self):
        body = json.dumps(success_plan()) + json.dumps(refusal_plan())
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=FakeGemmaTransport({"output_text": body}),
        )

        with self.assertRaises(GemmaLocalProviderError) as raised:
            provider.generate_plan(safe_context("Read status.read from lamp_1."))

        self.assertEqual(raised.exception.code, AI_RESPONSE_INVALID)

    def test_malformed_empty_and_non_object_responses_are_safe_errors(self):
        cases = [
            "",
            "not json",
            "[]",
            {},
            {"output_text": ""},
            {"tool_calls": [{"function": {"name": "other", "arguments": {}}}]},
            {
                "tool_calls": [
                    {"function": {"name": "ai_action_plan", "arguments": success_plan()}},
                    {"function": {"name": "ai_action_plan", "arguments": refusal_plan()}},
                ]
            },
        ]
        for body in cases:
            with self.subTest(body=body):
                provider = GemmaLocalAIProvider(
                    GemmaLocalProviderConfig("gemma-4-e2b"),
                    transport=FakeGemmaTransport(body),
                )
                with self.assertRaises(GemmaLocalProviderError) as raised:
                    provider.generate_plan(safe_context("test"))
                self.assertEqual(raised.exception.code, AI_RESPONSE_INVALID)

    def test_oversized_response_timeout_and_transport_exception_are_safe_errors(self):
        oversized = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b", maximum_response_bytes=1024),
            transport=FakeGemmaTransport(success_plan(), body_size_bytes=1025),
        )
        oversized_absolute = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b", maximum_response_bytes=1024),
            transport=FakeGemmaTransport(success_plan(), body_size_bytes=1024 * 1024),
        )
        timeout = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=RaisingTransport(TimeoutError("raw timeout detail")),
        )
        unavailable = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=RaisingTransport(RuntimeError("raw bridge detail")),
        )

        with self.assertRaises(GemmaLocalProviderError) as raised:
            oversized.generate_plan(safe_context("test"))
        self.assertEqual(raised.exception.code, AI_RESPONSE_TOO_LARGE)
        with self.assertRaises(GemmaLocalProviderError) as raised:
            oversized_absolute.generate_plan(safe_context("test"))
        self.assertEqual(raised.exception.code, AI_RESPONSE_TOO_LARGE)
        with self.assertRaises(GemmaLocalProviderError) as raised:
            timeout.generate_plan(safe_context("test"))
        self.assertEqual(raised.exception.code, AI_PROVIDER_TIMEOUT)
        self.assertNotIn("raw timeout detail", str(raised.exception))
        with self.assertRaises(GemmaLocalProviderError) as raised:
            unavailable.generate_plan(safe_context("test"))
        self.assertEqual(raised.exception.code, AI_PROVIDER_UNAVAILABLE)
        self.assertNotIn("raw bridge detail", str(raised.exception))

    def test_large_body_with_lying_body_size_bytes_still_rejects(self):
        large_body = {"output_text": "x" * 4096}
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b", maximum_response_bytes=1024),
            transport=FakeGemmaTransport(large_body, body_size_bytes=1),
        )

        with self.assertRaises(GemmaLocalProviderError) as raised:
            provider.generate_plan(safe_context("test"))

        self.assertEqual(raised.exception.code, AI_RESPONSE_TOO_LARGE)

    def test_unconfigured_transport_ignores_host_specific_request_details(self):
        transport = UnconfiguredGemmaLocalTransport()

        with self.assertRaises(GemmaLocalProviderError) as raised:
            transport.generate({}, timeout_seconds=1, max_response_bytes=1024)

        self.assertEqual(raised.exception.code, AI_PROVIDER_UNAVAILABLE)

    def test_provider_module_does_not_import_execution_voice_or_stt_boundaries(self):
        source = Path("jarvis_core/ai/gemma_local.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

        forbidden = (
            "jarvis_core.runtime",
            "jarvis_core.drivers",
            "jarvis_core.device_state",
            "jarvis_core.api",
            "jarvis_core.dashboard",
            "jarvis_core.voice",
            "jarvis_core.planner",
        )
        self.assertFalse(
            any(module.startswith(forbidden) for module in imported_modules),
            imported_modules,
        )


def safe_context(request):
    return SafeContextBuilder().build(request, test_runtime().context.device_registry)


def _fixture(fixture_id):
    return next(
        fixture
        for fixture in build_default_structured_ai_fixtures()
        if fixture.fixture_id == fixture_id
    )


def success_plan(command="device read lamp_1 status.read"):
    return {
        "schema_version": 1,
        "kind": "execute",
        "steps": [
            {
                "index": 0,
                "canonical_command_text": command,
                "safe_description": command,
                "target_device_id": "lamp_1",
                "capability_name": "status.read",
                "action_kind": "read",
                "requires_confirmation": False,
                "policy_flags": [],
            }
        ],
        "safe_summary": "Plan seguro.",
        "clarification": None,
        "refusal": None,
        "confirmation_required": False,
        "policy_flags": [],
    }


def clarify_plan():
    return {
        "schema_version": 1,
        "kind": "clarify",
        "steps": [],
        "safe_summary": "Falta elegir dispositivo.",
        "clarification": {
            "question": "¿Qué luz quieres usar?",
            "reason_code": "ambiguous_device",
            "missing_fields": ["device_id"],
            "candidate_options": ["lamp_1", "lamp_2"],
        },
        "refusal": None,
        "confirmation_required": False,
        "policy_flags": [],
    }


def refusal_plan():
    return {
        "schema_version": 1,
        "kind": "refuse",
        "steps": [],
        "safe_summary": "Solicitud rechazada.",
        "clarification": None,
        "refusal": {
            "safe_message": "No puedo realizar esa solicitud.",
            "reason_code": "forbidden_operation",
        },
        "confirmation_required": False,
        "policy_flags": [],
    }


class FakeGemmaTransport:
    def __init__(self, body, *, body_size_bytes=None):
        self.body = body
        self.body_size_bytes = body_size_bytes
        self.calls = []

    def generate(self, request, timeout_seconds, max_response_bytes):
        self.calls.append(
            {
                "request": request,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        return GemmaLocalResponse(self.body, self.body_size_bytes)


class RaisingTransport:
    def __init__(self, error):
        self.error = error

    def generate(self, request, timeout_seconds, max_response_bytes):
        raise self.error


if __name__ == "__main__":
    unittest.main()
