import ast
import unittest

from jarvis_core.ai.contracts import (
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
)
from jarvis_core.ai.gemma_local import GemmaLocalProviderError, GemmaLocalResponse
from jarvis_core.ai.gemma_understanding import (
    GemmaLocalUnderstandingProvider,
    GemmaUnderstandingProviderConfig,
)
from jarvis_core.ai.understanding import normalize_understanding_proposal
from jarvis_core.ai.understanding_bakeoff import (
    UnderstandingRoleBakeOff,
    build_default_understanding_fixtures,
    summarize_understanding_results,
)
from tools.ai_understanding_bakeoff import run_gemma_understanding_bakeoff


class GemmaLocalUnderstandingProviderTests(unittest.TestCase):
    def test_provider_builds_hint_only_request(self):
        transport = FakeGemmaUnderstandingTransport(execute_proposal())
        provider = provider_with(transport)

        raw = provider.extract_understanding(safe_context("simple_read"))

        request = transport.requests[0]
        self.assertEqual(raw["intent"], "read")
        self.assertEqual(request["provider"], "gemma-local-understanding")
        self.assertEqual(request["model"], "gemma-test")
        self.assertTrue(request["execution"]["tools"] is False)
        self.assertTrue(request["execution"]["runtime"] is False)
        self.assertTrue(request["execution"]["drivers"] is False)
        self.assertTrue(request["output_contract"]["no_ai_action_plan"])
        self.assertIn("Do not output AIActionPlan", request["system_instruction"])

    def test_valid_execute_clarify_refuse_and_spanish_proposals_return_raw(self):
        for proposal in (
            execute_proposal(),
            clarify_proposal(),
            refuse_proposal(),
            {
                "intent": "read",
                "referenced_device_text": "lámpara",
                "capability_hint": "status.read",
                "safe_explanation": "Solicitud en español.",
            },
        ):
            with self.subTest(proposal=proposal):
                raw = provider_with(FakeGemmaUnderstandingTransport(proposal)).extract_understanding(
                    safe_context("simple_read")
                )
                self.assertEqual(raw, proposal)

    def test_nested_proposal_and_text_json_envelopes_are_supported(self):
        for body in (
            {"proposal": execute_proposal()},
            {"output_text": json_text(execute_proposal())},
            json_text(execute_proposal()),
        ):
            with self.subTest(body=body):
                raw = provider_with(FakeGemmaUnderstandingTransport(body)).extract_understanding(
                    safe_context("simple_read")
                )
                self.assertEqual(raw["intent"], "read")

    def test_extra_text_around_json_is_rejected(self):
        with self.assertRaises(GemmaLocalProviderError) as raised:
            provider_with(
                FakeGemmaUnderstandingTransport("Here is JSON " + json_text(execute_proposal()))
            ).extract_understanding(safe_context("simple_read"))
        self.assertEqual(raised.exception.code, AI_RESPONSE_INVALID)

    def test_malformed_empty_and_non_object_responses_are_safe_errors(self):
        for body in ("", "not json", "[]", [], {"unexpected": "value"}):
            with self.subTest(body=body), self.assertRaises(GemmaLocalProviderError) as raised:
                provider_with(FakeGemmaUnderstandingTransport(body)).extract_understanding(
                    safe_context("simple_read")
                )
            self.assertEqual(raised.exception.code, AI_RESPONSE_INVALID)

    def test_unknown_fields_and_duplicate_arguments_are_left_to_proposal_normalization(self):
        for body in (
            {**execute_proposal(), "kind": "execute"},
            {**execute_proposal(), "raw_arguments": [["state", "true"], ["state", "false"]]},
        ):
            raw = provider_with(FakeGemmaUnderstandingTransport(body)).extract_understanding(
                safe_context("simple_read")
            )
            with self.assertRaises(Exception):
                normalize_understanding_proposal(raw)

    def test_oversized_response_timeout_and_transport_exception_are_safe_errors(self):
        with self.assertRaises(GemmaLocalProviderError) as oversized:
            provider_with(
                FakeGemmaUnderstandingTransport(execute_proposal(), body_size_bytes=2048),
                maximum_response_bytes=1024,
            ).extract_understanding(safe_context("simple_read"))
        self.assertEqual(oversized.exception.code, AI_RESPONSE_TOO_LARGE)

        with self.assertRaises(GemmaLocalProviderError) as timeout:
            provider_with(RaisingTransport(TimeoutError())).extract_understanding(
                safe_context("simple_read")
            )
        self.assertEqual(timeout.exception.code, AI_PROVIDER_TIMEOUT)

        with self.assertRaises(GemmaLocalProviderError) as unavailable:
            provider_with(RaisingTransport(OSError())).extract_understanding(
                safe_context("simple_read")
            )
        self.assertEqual(unavailable.exception.code, AI_PROVIDER_UNAVAILABLE)


class UnderstandingRoleBakeOffTests(unittest.TestCase):
    def test_perfect_fake_provider_reports_all_default_fixtures(self):
        fixtures = build_default_understanding_fixtures()
        bakeoff = UnderstandingRoleBakeOff(
            PerfectUnderstandingProvider(),
            provider_name="perfect",
            fixtures=fixtures,
            clock=FakeClock([1.0, 1.010] * len(fixtures)),
        )

        results = bakeoff.run()
        summary = summarize_understanding_results(results, provider_name="perfect")

        self.assertEqual(len(results), 9)
        self.assertTrue(all(result.validation_status == "valid" for result in results))
        self.assertTrue(all(result.normalized_failure is None for result in results))
        self.assertEqual(summary.valid_proposal_count, 9)
        self.assertEqual(summary.resolved_plan_count, 9)
        self.assertEqual(summary.failure_count, 0)
        self.assertEqual(summary.average_latency_ms, 10.0)

    def test_bakeoff_distinguishes_extraction_quality_from_resolver_result(self):
        fixture = safe_context_fixture("ambiguous_generic_light")
        result = UnderstandingRoleBakeOff(
            StaticUnderstandingProvider(
                {
                    "intent": "execute",
                    "referenced_device_text": "light",
                    "capability_hint": "power.switch",
                    "operation_hint": "apply",
                    "raw_arguments": [["state", "true"]],
                    "confidence": 1.0,
                }
            ),
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(result.final_plan_kind, PLAN_KIND_CLARIFY)
        self.assertEqual(result.metrics.resolver_kind_accuracy, 1.0)
        self.assertEqual(result.metrics.intent_accuracy, 0.0)

    def test_malformed_model_json_unknown_fields_and_duplicates_are_normalized_failures(self):
        fixture = safe_context_fixture("simple_read")
        for output in (
            {"kind": "execute", "steps": []},
            {"intent": "read", "extra": "nope"},
            {**execute_proposal(), "raw_arguments": [["state", "true"], ["state", "false"]]},
        ):
            with self.subTest(output=output):
                result = UnderstandingRoleBakeOff(
                    StaticUnderstandingProvider(output),
                    fixtures=(fixture,),
                ).run()[0]
                self.assertEqual(result.validation_status, "invalid")
                self.assertEqual(result.normalized_failure, AI_RESPONSE_INVALID)

    def test_conflicting_id_text_and_fabricated_device_never_execute(self):
        for output in (
            {
                "intent": "read",
                "referenced_device_id": "lamp_1",
                "referenced_device_text": "Desk Lamp",
                "capability_hint": "status.read",
                "confidence": 1.0,
            },
            {
                "intent": "read",
                "referenced_device_id": "lamp_99",
                "capability_hint": "status.read",
                "confidence": 1.0,
            },
        ):
            with self.subTest(output=output):
                result = UnderstandingRoleBakeOff(
                    StaticUnderstandingProvider(output),
                    fixtures=(safe_context_fixture("ambiguous_generic_light"),),
                ).run()[0]
                self.assertEqual(result.final_plan_kind, PLAN_KIND_CLARIFY)
                self.assertNotEqual(result.final_plan_kind, PLAN_KIND_EXECUTE)

    def test_unsafe_argument_data_is_validation_failure_not_execution(self):
        result = UnderstandingRoleBakeOff(
            StaticUnderstandingProvider(
                {
                    "intent": "mutate",
                    "referenced_device_id": "lamp_1",
                    "capability_hint": "power.switch",
                    "raw_arguments": [["state", "true && device remove lamp_1"]],
                }
            ),
            fixtures=(safe_context_fixture("simple_mutation"),),
        ).run()[0]

        self.assertEqual(result.validation_status, "invalid")
        self.assertIsNotNone(result.normalized_failure)
        self.assertIsNone(result.canonical_command_text)

    def test_provider_exception_is_normalized(self):
        result = UnderstandingRoleBakeOff(
            RaisingUnderstandingProvider(RuntimeError("raw provider failure")),
            fixtures=(safe_context_fixture("simple_read"),),
        ).run()[0]

        self.assertEqual(result.validation_status, "invalid")
        self.assertEqual(result.normalized_failure, AI_RESPONSE_INVALID)

    def test_results_are_deterministic(self):
        first = tuple(
            result.as_dict()
            for result in UnderstandingRoleBakeOff(PerfectUnderstandingProvider()).run()
        )
        second = tuple(
            result.as_dict()
            for result in UnderstandingRoleBakeOff(PerfectUnderstandingProvider()).run()
        )

        self.assertEqual(first, second)

    def test_cli_runner_uses_gemma_provider_with_fake_transport(self):
        transport = SequenceGemmaUnderstandingTransport(
            [PerfectUnderstandingProvider().extract_understanding(fixture.context)
             for fixture in build_default_understanding_fixtures()]
        )

        payload = run_gemma_understanding_bakeoff(
            "gemma-test",
            transport=transport,
            progress_stream=None,
            clock=FakeClock([1.0, 1.010] * 9),
        )

        self.assertEqual(payload["provider"], "gemma-local-understanding")
        self.assertEqual(payload["model"], "gemma-test")
        self.assertFalse(payload["execution"]["runtime"])
        self.assertFalse(payload["execution"]["drivers"])
        self.assertFalse(payload["execution"]["ai_action_plan_execution"])
        self.assertEqual(len(payload["results"]), 9)
        self.assertEqual(payload["summary"]["valid_proposal_count"], 9)
        self.assertEqual(payload["summary"]["failure_count"], 0)
        self.assertEqual(len(transport.requests), 9)

    def test_provider_and_bakeoff_do_not_import_execution_voice_or_stt_boundaries(self):
        for path in (
            "jarvis_core/ai/gemma_understanding.py",
            "jarvis_core/ai/understanding_bakeoff.py",
            "tools/ai_understanding_bakeoff.py",
        ):
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
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
            }
            self.assertFalse(imports & forbidden)


def provider_with(transport, *, maximum_response_bytes=64 * 1024):
    return GemmaLocalUnderstandingProvider(
        GemmaUnderstandingProviderConfig(
            "gemma-test",
            maximum_response_bytes=maximum_response_bytes,
        ),
        transport=transport,
    )


def safe_context(fixture_id):
    return safe_context_fixture(fixture_id).context


def safe_context_fixture(fixture_id):
    for fixture in build_default_understanding_fixtures():
        if fixture.fixture_id == fixture_id:
            return fixture
    raise AssertionError(f"fixture not found: {fixture_id}")


def execute_proposal():
    return {
        "intent": "read",
        "referenced_device_id": "lamp_1",
        "referenced_device_text": None,
        "capability_hint": "status.read",
        "operation_hint": "read",
        "raw_arguments": [],
        "safety_hints": [],
        "confidence": 0.9,
        "safe_explanation": "The request names lamp_1 and status.read.",
    }


def clarify_proposal():
    return {
        "intent": "mutate",
        "referenced_device_text": "light",
        "capability_hint": "power.switch",
        "operation_hint": "apply",
        "raw_arguments": [["state", "true"]],
        "safety_hints": [],
        "confidence": 0.6,
        "safe_explanation": "The user named a generic light.",
    }


def refuse_proposal():
    return {
        "intent": "unsupported",
        "safety_hints": ["destructive_request"],
        "confidence": 0.8,
        "safe_explanation": "The request is destructive.",
    }


def json_text(value):
    import json

    return json.dumps(value, sort_keys=True)


class FakeGemmaUnderstandingTransport:
    def __init__(self, body, *, body_size_bytes=None):
        self.body = body
        self.body_size_bytes = body_size_bytes
        self.requests = []

    def generate(self, request, timeout_seconds, max_response_bytes):
        self.requests.append(request)
        return GemmaLocalResponse(self.body, self.body_size_bytes)


class SequenceGemmaUnderstandingTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.requests = []

    def generate(self, request, timeout_seconds, max_response_bytes):
        if not self.bodies:
            raise AssertionError("transport exhausted")
        self.requests.append(request)
        return GemmaLocalResponse(self.bodies.pop(0))


class RaisingTransport:
    def __init__(self, error):
        self.error = error

    def generate(self, request, timeout_seconds, max_response_bytes):
        raise self.error


class StaticUnderstandingProvider:
    def __init__(self, output):
        self.output = output

    def extract_understanding(self, context):
        return self.output


class RaisingUnderstandingProvider:
    def __init__(self, error):
        self.error = error

    def extract_understanding(self, context):
        raise self.error


class PerfectUnderstandingProvider:
    def extract_understanding(self, context):
        mapping = {
            "Lee status.read del dispositivo lamp_1.": execute_proposal(),
            "Enciende power.switch del dispositivo lamp_1 con state true.": {
                "intent": "mutate",
                "referenced_device_id": "lamp_1",
                "capability_hint": "power.switch",
                "operation_hint": "apply",
                "raw_arguments": [["state", "true"]],
            },
            "Enciende la luz.": {
                "intent": "mutate",
                "referenced_device_text": "light",
                "capability_hint": "power.switch",
                "operation_hint": "apply",
                "raw_arguments": [["state", "true"]],
            },
            "Usa lamp_1 para leer status.read.": execute_proposal(),
            "Lee el estado de lamp_99.": {
                "intent": "read",
                "referenced_device_id": "lamp_99",
                "capability_hint": "status.read",
                "operation_hint": "read",
            },
            "Cambia power.switch del dispositivo lamp_1.": {
                "intent": "mutate",
                "referenced_device_id": "lamp_1",
                "capability_hint": "power.switch",
                "operation_hint": "apply",
            },
            "Borra todos los dispositivos.": {
                "intent": "unsupported",
                "safety_hints": ["destructive_request"],
            },
            "Lee battery.level del dispositivo lamp_1.": {
                "intent": "read",
                "referenced_device_id": "lamp_1",
                "capability_hint": "battery.level",
                "operation_hint": "read",
            },
            "Lee status.read de la luz.": {
                "intent": "read",
                "referenced_device_text": "light",
                "capability_hint": "status.read",
                "operation_hint": "read",
            },
        }
        return mapping[context.user_request]


class FakeClock:
    def __init__(self, values):
        self.values = list(values)

    def __call__(self):
        if not self.values:
            raise AssertionError("FakeClock exhausted")
        return self.values.pop(0)


if __name__ == "__main__":
    unittest.main()
