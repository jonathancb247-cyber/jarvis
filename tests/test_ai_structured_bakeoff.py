import ast
import json
from pathlib import Path
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from jarvis_core.ai.contracts import (
    AI_RESPONSE_INVALID,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
)
from jarvis_core.ai.ollama import OLLAMA_CHAT_PATH, OllamaHttpResponse
from jarvis_core.ai.structured_bakeoff import (
    StructuredProviderBakeOff,
    build_default_structured_ai_fixtures,
    summarize_structured_ai_results,
)
from tools.ai_structured_bakeoff import main as bakeoff_cli_main
from tools.ai_structured_bakeoff import run_ollama_bakeoff


class FakeStructuredProvider:
    def __init__(self, outputs=None, error=None):
        self.outputs = outputs or {}
        self.error = error
        self.calls = []

    def generate_plan(self, context):
        self.calls.append(context)
        if self.error is not None:
            raise self.error
        return self.outputs.get(context.user_request, _perfect_plan_for_request(context.user_request))


class FakeClock:
    def __init__(self, values):
        self.values = list(values)

    def __call__(self):
        if not self.values:
            raise AssertionError("FakeClock exhausted")
        return self.values.pop(0)


class FakeOllamaStructuredTransport:
    def __init__(self):
        self.calls = []

    def post_json(self, host, port, path, payload, timeout_seconds, max_response_bytes):
        self.calls.append(
            {
                "host": host,
                "port": port,
                "path": path,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        user_content = next(
            message["content"] for message in payload["messages"] if message["role"] == "user"
        )
        user_request = json.loads(user_content)["user_request"]
        body = {
            "message": {
                "role": "assistant",
                "content": json.dumps(_perfect_plan_for_request(user_request)),
            },
            "done": True,
        }
        return OllamaHttpResponse(200, body)


class StructuredAIBakeOffTests(unittest.TestCase):
    def test_perfect_fake_provider_passes_all_default_fixtures(self):
        provider = FakeStructuredProvider()
        results = StructuredProviderBakeOff(provider, provider_name="perfect").run()

        self.assertEqual(len(results), 6)
        self.assertEqual(len(provider.calls), 6)
        for result in results:
            with self.subTest(fixture=result.fixture_id):
                self.assertIsNone(result.normalized_failure)
                self.assertEqual(result.metrics.ai_action_plan_valid, 1.0)
                self.assertEqual(result.metrics.kind_accuracy, 1.0)
                self.assertEqual(result.metrics.canonical_command_accuracy, 1.0)
                self.assertEqual(result.metrics.device_id_accuracy, 1.0)
                self.assertEqual(result.metrics.capability_accuracy, 1.0)
                self.assertEqual(result.metrics.argument_accuracy, 1.0)
                self.assertEqual(result.metrics.relative_time_reasoning, 1.0)
                self.assertEqual(result.metrics.clarification_correctness, 1.0)
                self.assertEqual(result.metrics.refusal_correctness, 1.0)

    def test_default_fixtures_cover_edge_gallery_checkpoint_risks(self):
        fixtures = build_default_structured_ai_fixtures()
        fixture_ids = {fixture.fixture_id for fixture in fixtures}
        tags = {tag for fixture in fixtures for tag in fixture.tags}

        self.assertIn("spanish_simple_read", fixture_ids)
        self.assertIn("english_simple_read", fixture_ids)
        self.assertIn("absolute_time_read", fixture_ids)
        self.assertIn("relative_time_two_minutes", fixture_ids)
        self.assertIn("ambiguous_device_clarify", fixture_ids)
        self.assertIn("unsupported_destructive_refusal", fixture_ids)
        self.assertIn("gemma_checkpoint", tags)
        relative = next(
            fixture
            for fixture in fixtures
            if fixture.fixture_id == "relative_time_two_minutes"
        )
        self.assertIn("current_time=2026-09-01T12:00:00Z", relative.context.session_context)

    def test_structurally_invalid_output_is_normalized(self):
        fixture = _fixture("spanish_simple_read")
        provider = FakeStructuredProvider({fixture.user_request: {"kind": PLAN_KIND_EXECUTE}})

        result = StructuredProviderBakeOff(
            provider,
            provider_name="invalid",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(result.normalized_failure, AI_RESPONSE_INVALID)
        self.assertEqual(result.metrics.ai_action_plan_valid, 0.0)
        self.assertIsNone(result.canonical_command_text)

    def test_canonical_command_incorrect_is_scored_without_execution(self):
        fixture = _fixture("spanish_simple_read")
        provider = FakeStructuredProvider(
            {
                fixture.user_request: _execute_plan(
                    "device read lamp_1 power.switch",
                    capability_name="power.switch",
                )
            }
        )

        result = StructuredProviderBakeOff(
            provider,
            provider_name="wrong-command",
            fixtures=(fixture,),
        ).run()[0]

        self.assertIsNone(result.normalized_failure)
        self.assertEqual(result.metrics.ai_action_plan_valid, 1.0)
        self.assertEqual(result.metrics.kind_accuracy, 1.0)
        self.assertEqual(result.metrics.canonical_command_accuracy, 0.0)
        self.assertEqual(result.metrics.capability_accuracy, 0.0)

    def test_argument_incorrect_is_scored_separately(self):
        fixture = _fixture("absolute_time_read")
        provider = FakeStructuredProvider(
            {
                fixture.user_request: _execute_plan(
                    "device read lamp_1 status.read schedule_at=2026-09-01T12:06:00Z",
                )
            }
        )

        result = StructuredProviderBakeOff(
            provider,
            provider_name="wrong-arg",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(result.metrics.ai_action_plan_valid, 1.0)
        self.assertEqual(result.metrics.kind_accuracy, 1.0)
        self.assertEqual(result.metrics.argument_accuracy, 0.0)
        self.assertEqual(result.metrics.relative_time_reasoning, 1.0)

    def test_relative_time_incorrect_is_scored_from_fixed_context(self):
        fixture = _fixture("relative_time_two_minutes")
        provider = FakeStructuredProvider(
            {
                fixture.user_request: _execute_plan(
                    "device read lamp_1 status.read schedule_at=2026-09-01T12:01:00Z",
                )
            }
        )

        result = StructuredProviderBakeOff(
            provider,
            provider_name="bad-time",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(result.metrics.ai_action_plan_valid, 1.0)
        self.assertEqual(result.metrics.argument_accuracy, 0.0)
        self.assertEqual(result.metrics.relative_time_reasoning, 0.0)

    def test_clarification_correct_and_incorrect_are_scored(self):
        fixture = _fixture("ambiguous_device_clarify")
        good = StructuredProviderBakeOff(
            FakeStructuredProvider({fixture.user_request: _clarify_plan()}),
            provider_name="clarify-good",
            fixtures=(fixture,),
        ).run()[0]
        bad = StructuredProviderBakeOff(
            FakeStructuredProvider({fixture.user_request: _execute_plan("device read lamp_1 status.read")}),
            provider_name="clarify-bad",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(good.metrics.kind_accuracy, 1.0)
        self.assertEqual(good.metrics.clarification_correctness, 1.0)
        self.assertEqual(bad.metrics.kind_accuracy, 0.0)
        self.assertEqual(bad.metrics.clarification_correctness, 0.0)

    def test_clarification_reason_and_missing_fields_are_scored(self):
        fixture = _fixture("ambiguous_device_clarify")
        wrong_reason = StructuredProviderBakeOff(
            FakeStructuredProvider(
                {
                    fixture.user_request: _clarify_plan(
                        reason_code="missing_parameter",
                        missing_fields=["device_id"],
                    )
                }
            ),
            provider_name="clarify-wrong-reason",
            fixtures=(fixture,),
        ).run()[0]
        missing_field = StructuredProviderBakeOff(
            FakeStructuredProvider(
                {
                    fixture.user_request: _clarify_plan(
                        reason_code="ambiguous_device",
                        missing_fields=[],
                    )
                }
            ),
            provider_name="clarify-missing-field",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(wrong_reason.metrics.ai_action_plan_valid, 1.0)
        self.assertEqual(wrong_reason.metrics.kind_accuracy, 1.0)
        self.assertEqual(wrong_reason.metrics.clarification_correctness, 0.0)
        self.assertEqual(missing_field.metrics.ai_action_plan_valid, 1.0)
        self.assertEqual(missing_field.metrics.kind_accuracy, 1.0)
        self.assertEqual(missing_field.metrics.clarification_correctness, 0.0)
        self.assertEqual(wrong_reason.clarification_reason_code, "missing_parameter")
        self.assertEqual(wrong_reason.clarification_missing_fields, ("device_id",))

    def test_refusal_correct_and_incorrect_are_scored(self):
        fixture = _fixture("unsupported_destructive_refusal")
        good = StructuredProviderBakeOff(
            FakeStructuredProvider({fixture.user_request: _refuse_plan()}),
            provider_name="refuse-good",
            fixtures=(fixture,),
        ).run()[0]
        bad = StructuredProviderBakeOff(
            FakeStructuredProvider({fixture.user_request: _clarify_plan()}),
            provider_name="refuse-bad",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(good.metrics.kind_accuracy, 1.0)
        self.assertEqual(good.metrics.refusal_correctness, 1.0)
        self.assertEqual(bad.metrics.kind_accuracy, 0.0)
        self.assertEqual(bad.metrics.refusal_correctness, 0.0)

    def test_refusal_reason_is_scored(self):
        fixture = _fixture("unsupported_destructive_refusal")

        result = StructuredProviderBakeOff(
            FakeStructuredProvider(
                {fixture.user_request: _refuse_plan(reason_code="unsupported_operation")}
            ),
            provider_name="refuse-wrong-reason",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(result.metrics.ai_action_plan_valid, 1.0)
        self.assertEqual(result.metrics.kind_accuracy, 1.0)
        self.assertEqual(result.metrics.refusal_correctness, 0.0)
        self.assertEqual(result.refusal_reason_code, "unsupported_operation")

    def test_result_serializes_observed_plan_details_for_audit(self):
        fixture = _fixture("absolute_time_read")
        result = StructuredProviderBakeOff(
            FakeStructuredProvider(
                {
                    fixture.user_request: _execute_plan(
                        "device read lamp_1 status.read schedule_at=2026-09-01T12:05:00Z",
                    )
                }
            ),
            provider_name="audit",
            fixtures=(fixture,),
        ).run()[0]

        payload = result.as_dict()

        self.assertEqual(payload["target_device_id"], "lamp_1")
        self.assertEqual(payload["capability_name"], "status.read")
        self.assertEqual(payload["action_kind"], "read")
        self.assertEqual(payload["arguments"], {"schedule_at": "2026-09-01T12:05:00Z"})
        self.assertIsNone(payload["clarification_reason_code"])
        self.assertEqual(payload["clarification_missing_fields"], [])
        self.assertIsNone(payload["refusal_reason_code"])

    def test_provider_exception_is_normalized(self):
        fixture = _fixture("spanish_simple_read")

        result = StructuredProviderBakeOff(
            FakeStructuredProvider(error=RuntimeError("raw provider failure")),
            provider_name="raises",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(result.normalized_failure, AI_RESPONSE_INVALID)
        self.assertEqual(result.metrics.ai_action_plan_valid, 0.0)
        self.assertNotIn("raw provider failure", repr(result.as_dict()))

    def test_harness_does_not_import_execution_boundaries(self):
        source = Path("jarvis_core/ai/structured_bakeoff.py").read_text(encoding="utf-8")
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
        )
        self.assertFalse(
            any(module.startswith(forbidden) for module in imported_modules),
            imported_modules,
        )

    def test_results_are_deterministic(self):
        first = tuple(result.as_dict() for result in StructuredProviderBakeOff(FakeStructuredProvider()).run())
        second = tuple(result.as_dict() for result in StructuredProviderBakeOff(FakeStructuredProvider()).run())

        self.assertEqual(first, second)

    def test_latency_is_measured_only_when_clock_is_injected(self):
        fixture = _fixture("spanish_simple_read")
        timed = StructuredProviderBakeOff(
            FakeStructuredProvider(),
            provider_name="timed",
            fixtures=(fixture,),
            clock=FakeClock([1.0, 1.125]),
        ).run()[0]
        untimed = StructuredProviderBakeOff(
            FakeStructuredProvider(),
            provider_name="untimed",
            fixtures=(fixture,),
        ).run()[0]

        self.assertEqual(timed.latency_ms, 125)
        self.assertIsNone(untimed.latency_ms)

    def test_summary_aggregates_fixture_metrics_and_latency(self):
        fixtures = (_fixture("spanish_simple_read"), _fixture("relative_time_two_minutes"))
        provider = FakeStructuredProvider(
            {
                fixtures[1].user_request: _execute_plan(
                    "device read lamp_1 status.read schedule_at=2026-09-01T12:01:00Z",
                )
            }
        )
        results = StructuredProviderBakeOff(
            provider,
            provider_name="mixed",
            fixtures=fixtures,
            clock=FakeClock([1.0, 1.100, 2.0, 2.200]),
        ).run()

        summary = summarize_structured_ai_results(
            results,
            provider_name="mixed",
            fixtures=fixtures,
        )

        self.assertEqual(summary.fixture_count, 2)
        self.assertEqual(summary.valid_plan_count, 2)
        self.assertEqual(summary.failure_count, 0)
        self.assertEqual(summary.average_latency_ms, 150)
        self.assertEqual(summary.average_metrics["ai_action_plan_valid"], 1.0)
        self.assertEqual(summary.average_metrics["relative_time_reasoning"], 0.5)
        self.assertEqual(summary.applicable_metric_counts["relative_time_reasoning"], 1)
        self.assertEqual(summary.applicable_average_metrics["relative_time_reasoning"], 0.0)
        self.assertEqual(summary.applicable_metric_counts["argument_accuracy"], 1)
        self.assertEqual(summary.applicable_average_metrics["argument_accuracy"], 0.0)
        self.assertEqual(summary.applicable_metric_counts["canonical_command_accuracy"], 2)

    def test_summary_can_remain_result_only_without_fixture_applicability(self):
        results = StructuredProviderBakeOff(FakeStructuredProvider()).run()

        summary = summarize_structured_ai_results(results, provider_name="no-fixtures")

        self.assertEqual(summary.fixture_count, 6)
        self.assertEqual(summary.applicable_metric_counts, {})
        self.assertEqual(summary.applicable_average_metrics, {})

    def test_ollama_cli_uses_real_provider_with_fake_transport(self):
        progress = StringIO()
        transport = FakeOllamaStructuredTransport()
        payload = run_ollama_bakeoff(
            "qwen3:4b",
            transport=transport,
            maximum_output_tokens=128,
            progress_stream=progress,
            clock=FakeClock([1.0, 1.010] * 6),
        )

        self.assertEqual(payload["provider"], "ollama")
        self.assertEqual(payload["model"], "qwen3:4b")
        self.assertEqual(payload["maximum_output_tokens"], 128)
        self.assertEqual(payload["fixed_temporal_context"], "current_time=2026-09-01T12:00:00Z")
        self.assertFalse(payload["execution"]["runtime"])
        self.assertFalse(payload["execution"]["drivers"])
        self.assertFalse(payload["execution"]["stt"])
        self.assertFalse(payload["execution"]["ai_action_plan_execution"])
        self.assertFalse(payload["execution"]["cloud_fallback"])
        self.assertEqual(len(payload["results"]), 6)
        self.assertEqual(payload["summary"]["fixture_count"], 6)
        self.assertEqual(payload["summary"]["failure_count"], 0)
        self.assertEqual(payload["summary"]["average_latency_ms"], 10)
        self.assertEqual(payload["summary"]["applicable_metric_counts"]["relative_time_reasoning"], 1)
        self.assertEqual(payload["summary"]["applicable_average_metrics"]["relative_time_reasoning"], 1.0)
        self.assertEqual(len(transport.calls), 6)
        for call in transport.calls:
            request = call["payload"]
            self.assertEqual(call["host"], "127.0.0.1")
            self.assertEqual(call["path"], OLLAMA_CHAT_PATH)
            self.assertEqual(request["model"], "qwen3:4b")
            self.assertIs(request["think"], False)
            self.assertIs(request["stream"], False)
            self.assertEqual(request["format"]["type"], "object")
            self.assertEqual(request["options"]["num_predict"], 128)
        progress_lines = progress.getvalue().splitlines()
        self.assertEqual(len(progress_lines), 12)
        self.assertEqual(progress_lines[0], "[1/6] running spanish_simple_read")
        self.assertIn("[6/6] finished unsupported_destructive_refusal: ok, 10ms", progress_lines)

    def test_ollama_cli_main_prints_canonical_json_report(self):
        class FakeProvider:
            def __init__(self, config, transport=None):
                self.config = config

            def generate_plan(self, context):
                return _perfect_plan_for_request(context.user_request)

        output = StringIO()
        progress = StringIO()
        with patch("tools.ai_structured_bakeoff.OllamaAIProvider", FakeProvider):
            with redirect_stdout(output), redirect_stderr(progress):
                result = bakeoff_cli_main(["ollama", "--model", "qwen3:4b"])

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["provider"], "ollama")
        self.assertEqual(payload["summary"]["fixture_count"], 6)
        self.assertEqual(payload["summary"]["valid_plan_count"], 6)
        self.assertIn("[1/6] running spanish_simple_read", progress.getvalue())

    def test_cli_tool_does_not_import_execution_boundaries(self):
        source = Path("tools/ai_structured_bakeoff.py").read_text(encoding="utf-8")
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
        )
        self.assertFalse(
            any(module.startswith(forbidden) for module in imported_modules),
            imported_modules,
        )


def _fixture(fixture_id):
    return next(
        fixture
        for fixture in build_default_structured_ai_fixtures()
        if fixture.fixture_id == fixture_id
    )


def _perfect_plan_for_request(user_request):
    fixtures = {
        fixture.user_request: fixture for fixture in build_default_structured_ai_fixtures()
    }
    fixture = fixtures[user_request]
    expectation = fixture.expectation
    if expectation.kind == PLAN_KIND_CLARIFY:
        return _clarify_plan()
    if expectation.kind == PLAN_KIND_REFUSE:
        return _refuse_plan()
    return _execute_plan(
        expectation.canonical_command_text,
        target_device_id=expectation.target_device_id,
        capability_name=expectation.capability_name,
        action_kind=expectation.action_kind,
    )


def _execute_plan(
    command,
    *,
    target_device_id="lamp_1",
    capability_name="status.read",
    action_kind="read",
):
    return {
        "schema_version": 1,
        "kind": "execute",
        "steps": [
            {
                "index": 0,
                "canonical_command_text": command,
                "safe_description": "Evaluated only; not executed.",
                "target_device_id": target_device_id,
                "capability_name": capability_name,
                "action_kind": action_kind,
                "requires_confirmation": False,
                "policy_flags": [],
            }
        ],
        "safe_summary": "Evaluation only.",
        "clarification": None,
        "refusal": None,
        "confirmation_required": False,
        "policy_flags": [],
    }


def _clarify_plan(reason_code="ambiguous_device", missing_fields=None):
    missing_fields = ["device_id"] if missing_fields is None else missing_fields
    return {
        "schema_version": 1,
        "kind": "clarify",
        "steps": [],
        "safe_summary": "Need clarification.",
        "clarification": {
            "question": "Which light do you mean?",
            "reason_code": reason_code,
            "missing_fields": missing_fields,
            "candidate_options": ["lamp_1", "lamp_2"],
        },
        "refusal": None,
        "confirmation_required": False,
        "policy_flags": [],
    }


def _refuse_plan(reason_code="forbidden_operation"):
    return {
        "schema_version": 1,
        "kind": "refuse",
        "steps": [],
        "safe_summary": "Unsupported destructive request.",
        "clarification": None,
        "refusal": {
            "safe_message": "I cannot delete devices.",
            "reason_code": reason_code,
        },
        "confirmation_required": False,
        "policy_flags": [],
    }


if __name__ == "__main__":
    unittest.main()
