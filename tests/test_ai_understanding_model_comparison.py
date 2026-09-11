import ast
import unittest
from pathlib import Path

from jarvis_core.ai.contracts import PLAN_KIND_CLARIFY, PLAN_KIND_EXECUTE, PLAN_KIND_REFUSE
from jarvis_core.ai.understanding_bakeoff import build_default_understanding_fixtures
from jarvis_core.ai.understanding_model_comparison import (
    ServerResponseRecord,
    is_android_json_rejection,
    is_unsafe_execute_escape,
    run_understanding_model_comparison,
)
from tests.test_ai_understanding_model_adapter import (
    PerfectUnderstandingProvider,
    RaisingUnderstandingProvider,
    SequenceGemmaUnderstandingTransport,
)
from tools.ai_understanding_compare import run_android_understanding_model_comparison


class UnderstandingModelComparisonTests(unittest.TestCase):
    def test_perfect_candidate_scores_perfect_metrics(self):
        report = run_understanding_model_comparison(
            {"perfect": PerfectUnderstandingProvider()},
            baseline_model="perfect",
            clock=RepeatingClock([1.0, 1.010]),
        )

        record = report.records[0]
        self.assertEqual(record.model, "perfect")
        self.assertEqual(record.fixture_count, 9)
        self.assertEqual(record.valid_proposal_count, 9)
        self.assertEqual(record.invalid_proposal_count, 0)
        self.assertEqual(record.resolved_plan_count, 9)
        self.assertEqual(record.failure_count, 0)
        self.assertEqual(record.android_json_rejection_count, 0)
        self.assertEqual(record.unsafe_execute_escapes, 0)
        for attribute in (
            "intent_accuracy",
            "device_id_accuracy",
            "device_text_accuracy",
            "device_resolution_accuracy",
            "capability_accuracy",
            "operation_accuracy",
            "argument_accuracy",
            "resolver_kind_accuracy",
            "canonical_command_accuracy",
        ):
            self.assertEqual(getattr(record, attribute), 1.0)
        self.assertEqual(record.average_latency_ms, 10.0)
        self.assertEqual(record.cold_latency_ms, 10.0)
        self.assertEqual(record.warm_latency_ms, 10.0)
        self.assertIsNone(record.memory_rss_mb)
        self.assertEqual(len(record.outcomes), 9)
        self.assertEqual(record.outcomes[0].cold_or_warm, "cold")
        self.assertEqual(record.outcomes[1].cold_or_warm, "warm")

    def test_report_explicitly_marks_execution_and_router_disconnected(self):
        report = run_understanding_model_comparison(
            {"perfect": PerfectUnderstandingProvider()},
            baseline_model="perfect",
        )
        payload = report.as_dict()

        self.assertEqual(payload["fixture_set"], "ai-understanding-role-bakeoff")
        self.assertEqual(payload["baseline_model"], "perfect")
        self.assertEqual(payload["models"], ["perfect"])
        for key in (
            "runtime",
            "drivers",
            "stt",
            "voice",
            "action_execution",
            "cloud_fallback",
            "model_router",
        ):
            self.assertFalse(payload["execution"][key])

    def test_resolver_authority_blocks_fabricated_proposals_from_executing(self):
        report = run_understanding_model_comparison(
            {"fabricating": FabricatingUnderstandingProvider()},
            baseline_model="fabricating",
            clock=RepeatingClock([1.0, 1.010]),
        )

        record = report.records[0]
        self.assertEqual(record.unsafe_execute_escapes, 0)
        self.assertEqual(record.unsafe_execute_escape_fixtures, ())
        self.assertLess(record.device_resolution_accuracy, 1.0)

    def test_failing_provider_fails_closed_with_no_escapes(self):
        report = run_understanding_model_comparison(
            {"mute": RaisingUnderstandingProvider(RuntimeError("muted"))},
            baseline_model="mute",
        )

        record = report.records[0]
        self.assertEqual(record.valid_proposal_count, 0)
        self.assertEqual(record.resolved_plan_count, 0)
        self.assertEqual(record.unsafe_execute_escapes, 0)
        self.assertEqual(record.invalid_proposal_count, 8)
        self.assertEqual(record.failure_count, 8)
        for outcome in record.outcomes:
            self.assertNotEqual(outcome.final_plan_kind, PLAN_KIND_EXECUTE)

    def test_android_json_rejections_are_counted_per_model(self):
        providers = {
            "gemma-a": PerfectUnderstandingProvider(),
            "gemma-b": PerfectUnderstandingProvider(),
        }
        records = {
            "gemma-a": lambda: (ServerResponseRecord(http_status=200) for _ in range(9)),
            "gemma-b": lambda: tuple(
                [
                    ServerResponseRecord.from_raw(500, b'{"error":"invalid_generation"}'),
                    ServerResponseRecord(http_status=200),
                    ServerResponseRecord.from_raw(500, b'{"error":"empty_generation"}'),
                ]
                + [ServerResponseRecord(http_status=200) for _ in range(6)]
            ),
        }
        report = run_understanding_model_comparison(
            providers,
            baseline_model="gemma-a",
            server_records=records,
        )

        by_model = {record.model: record.android_json_rejection_count for record in report.records}
        self.assertEqual(by_model["gemma-a"], 0)
        self.assertEqual(by_model["gemma-b"], 2)
        self.assertEqual(
            report.records[1].outcomes[0].server_response.error_code,
            "invalid_generation",
        )
        self.assertEqual(
            report.records[1].outcomes[2].server_response.body_size_bytes,
            len(b'{"error":"empty_generation"}'),
        )

    def test_cold_and_warm_latencies_are_reported_separately(self):
        clock = SequenceClock(
            [0.0, 0.042] + [1.0 + (0.005 * index) for index in range(16)]
        )
        report = run_understanding_model_comparison(
            {"perfect": PerfectUnderstandingProvider()},
            baseline_model="perfect",
            clock=clock,
        )

        record = report.records[0]
        self.assertEqual(record.cold_latency_ms, 42.0)
        self.assertEqual(record.warm_latency_ms, 5.0)
        self.assertEqual(record.average_latency_ms, 9.1)

    def test_memory_observation_records_only_when_provided(self):
        report = run_understanding_model_comparison(
            {"perfect": PerfectUnderstandingProvider()},
            baseline_model="perfect",
            memory_rss_mb={"perfect": 512.4},
        )
        self.assertEqual(report.records[0].memory_rss_mb, 512.4)
        self.assertEqual(report.records[0].as_dict()["memory_rss_mb"], 512.4)

    def test_runner_rejects_empty_or_mismatched_baseline(self):
        with self.assertRaises(ValueError):
            run_understanding_model_comparison({}, baseline_model="nope")
        with self.assertRaises(ValueError):
            run_understanding_model_comparison(
                {"perfect": PerfectUnderstandingProvider()},
                baseline_model="other",
            )

    def test_cli_runner_compares_models_via_injected_transports(self):
        fixtures = build_default_understanding_fixtures()
        bodies = [
            PerfectUnderstandingProvider().extract_understanding(fixture.context)
            for fixture in fixtures
        ]
        transports = {
            "gemma-a": RecordingSequenceTransport(list(bodies)),
            "gemma-b": RecordingSequenceTransport(list(bodies)),
        }
        payload = run_android_understanding_model_comparison(
            ["gemma-a", "gemma-b"],
            baseline_model="gemma-a",
            transport_factory=lambda model: transports[model],
            progress_stream=None,
            clock=RepeatingClock([1.0, 1.010]),
        )

        self.assertEqual(payload["baseline_model"], "gemma-a")
        self.assertEqual(payload["model_count"], 2)
        self.assertFalse(payload["execution"]["runtime"])
        self.assertFalse(payload["execution"]["model_router"])
        for record in payload["records"]:
            self.assertEqual(record["fixture_count"], 9)
            self.assertEqual(record["valid_proposal_count"], 9)
            self.assertEqual(record["resolver_kind_accuracy"], 1.0)
            self.assertEqual(record["canonical_command_accuracy"], 1.0)
            self.assertEqual(record["device_resolution_accuracy"], 1.0)
            self.assertEqual(record["unsafe_execute_escapes"], 0)
            self.assertEqual(record["cold_latency_ms"], 10.0)
            self.assertEqual(record["warm_latency_ms"], 10.0)

    def test_comparison_and_cli_do_not_import_execution_voice_or_stt_boundaries(self):
        for path in (
            "jarvis_core/ai/understanding_model_comparison.py",
            "jarvis_core/ai/gemma_android_bridge.py",
            "tools/ai_understanding_compare.py",
        ):
            with self.subTest(path=path):
                tree = ast.parse(Path(path).read_text(encoding="utf-8"))
                imported = {
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                imported.update(
                    node.module
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module is not None
                )
                forbidden = (
                    "jarvis_core.runtime",
                    "jarvis_core.drivers",
                    "jarvis_core.http_driver",
                    "jarvis_core.mqtt_driver",
                    "jarvis_core.voice",
                    "jarvis_core.api",
                    "jarvis_core.dashboard",
                    "jarvis_core.ai.adapter",
                    "jarvis_core.planner",
                )
                self.assertFalse(
                    any(module.startswith(forbidden) for module in imported),
                    path,
                )


class ServerResponseRecordTests(unittest.TestCase):
    def test_from_raw_extracts_error_code_size_and_bounded_excerpt(self):
        raw = b'{"error":"invalid_generation","message":"boo"}'
        record = ServerResponseRecord.from_raw(500, raw)

        self.assertEqual(record.http_status, 500)
        self.assertEqual(record.error_code, "invalid_generation")
        self.assertEqual(record.body_size_bytes, len(raw))
        self.assertIn("invalid_generation", record.body_excerpt)

    def test_from_raw_handles_non_json_and_empty_bodies_without_raising(self):
        for raw in (None, b"", b"not-json", b"[]"):
            with self.subTest(raw=raw):
                record = ServerResponseRecord.from_raw(500, raw)
                self.assertIsNone(record.error_code)


class EscapeMetricUnitTests(unittest.TestCase):
    def test_unsafe_execute_escape_only_fires_for_unexpected_execute(self):
        cases = [
            ("execute", "execute", False),
            ("execute", "clarify", False),
            ("clarify", "execute", True),
            ("refuse", "execute", True),
            ("clarify", "clarify", False),
            ("refuse", None, False),
        ]
        for expected, final, escapes in cases:
            with self.subTest(expected=expected, final=final):
                self.assertEqual(
                    is_unsafe_execute_escape(expected, final),
                    escapes,
                )
        self.assertFalse(is_unsafe_execute_escape(PLAN_KIND_EXECUTE, PLAN_KIND_EXECUTE))
        self.assertTrue(is_unsafe_execute_escape(PLAN_KIND_REFUSE, PLAN_KIND_EXECUTE))


class AndroidJsonRejectionUnitTests(unittest.TestCase):
    def test_rejection_detection_is_status_and_error_code_based(self):
        self.assertTrue(
            is_android_json_rejection(
                ServerResponseRecord.from_raw(500, b'{"error":"invalid_generation"}')
            )
        )
        self.assertTrue(
            is_android_json_rejection(
                ServerResponseRecord.from_raw(500, b'{"error":"empty_generation"}')
            )
        )
        self.assertFalse(
            is_android_json_rejection(
                ServerResponseRecord.from_raw(500, b'{"error":"server_broken"}')
            )
        )
        self.assertFalse(
            is_android_json_rejection(
                ServerResponseRecord.from_raw(200, b'{"error":"invalid_generation"}')
            )
        )


class FabricatingUnderstandingProvider:
    """Always emits a grounded but wrong/limited lamp_1 read proposal."""

    def extract_understanding(self, context):
        return {
            "intent": "read",
            "referenced_device_id": "lamp_1",
            "referenced_device_text": None,
            "capability_hint": "status.read",
            "operation_hint": "read",
            "raw_arguments": [],
            "confidence": 1.0,
            "safe_explanation": "Fabricated hint for comparison testing.",
        }


class RepeatingClock:
    def __init__(self, values):
        self.values = list(values)

    def __call__(self):
        values = self.values
        value = values[0]
        values.append(values.pop(0))
        return value


class SequenceClock:
    def __init__(self, values):
        self.values = list(values)

    def __call__(self):
        if not self.values:
            raise AssertionError("SequenceClock exhausted")
        return self.values.pop(0)


class RecordingSequenceTransport(SequenceGemmaUnderstandingTransport):
    def __init__(self, bodies):
        super().__init__(bodies)
        self.records = []


if __name__ == "__main__":
    unittest.main()