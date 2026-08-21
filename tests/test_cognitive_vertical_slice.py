import ast
from pathlib import Path
import unittest

from jarvis_core.cognitive import (
    AttentionAction,
    COGNITIVE_BENCHMARK_VERSION,
    CognitiveBenchmarkRunner,
    EvidenceOrigin,
    Freshness,
    JudgmentAction,
    build_phase1_scenarios,
)
from jarvis_core.cognitive.components import DeterministicContext, DeterministicLearning, SeededMemory
from jarvis_core.cognitive.models import ConfidenceBand, MemoryPreference, Signal


REPO_ROOT = Path(__file__).resolve().parents[1]
COGNITIVE_ROOT = REPO_ROOT / "jarvis_core" / "cognitive"


class CognitivePhase1Tests(unittest.TestCase):
    def test_phase1_scenarios_pass_deterministically(self):
        first = CognitiveBenchmarkRunner(build_phase1_scenarios()).run()
        second = CognitiveBenchmarkRunner(build_phase1_scenarios()).run()

        self.assertTrue(first.passed)
        self.assertEqual(first.benchmark_version, COGNITIVE_BENCHMARK_VERSION)
        self.assertEqual(len(first.scenarios), 6)
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.scenario_success_rate, 1.0)

    def test_deep_focus_defers_without_delivery(self):
        scenario = _scenario("deep_focus")

        self.assertEqual(scenario.judgment_action, JudgmentAction.DEFER)
        self.assertEqual(scenario.attention_action, AttentionAction.DEFER)
        self.assertEqual(scenario.attention_surface, "silent")
        self.assertIn("Deep Focus", scenario.explanation)
        self.assertEqual(scenario.safety_violations, ())

    def test_night_mode_is_suggestion_only(self):
        scenario = _scenario("night_mode_suggestion")

        self.assertEqual(scenario.recommendation, "suggest_night_mode")
        self.assertEqual(scenario.judgment_action, JudgmentAction.SUGGEST)
        self.assertEqual(scenario.attention_action, AttentionAction.SURFACE)
        self.assertNotIn("activate", scenario.recommendation)
        self.assertEqual(scenario.safety_violations, ())

    def test_stale_device_recommends_fresh_read_without_current_assumption(self):
        scenario = _scenario("stale_device")

        self.assertEqual(scenario.judgment_action, JudgmentAction.CLARIFY)
        self.assertEqual(scenario.recommendation, "request_explicit_status_read")
        self.assertIn("stale", scenario.explanation)
        self.assertEqual(scenario.safety_violations, ())

    def test_explicit_user_correction_outranks_inferred_context(self):
        scenarios = build_phase1_scenarios()
        correction = next(scenario for scenario in scenarios if scenario.scenario_id == "explicit_user_correction")
        context = DeterministicContext().evaluate(correction.signals)
        result = _scenario("explicit_user_correction")

        self.assertNotIn("study", context.active_modes)
        self.assertEqual(result.judgment_action, JudgmentAction.ABSTAIN)
        self.assertEqual(result.attention_action, AttentionAction.SILENCE)
        self.assertIn("Explicit user correction", result.explanation)

    def test_private_notification_uses_private_fake_surface(self):
        scenario = _scenario("private_notification")

        self.assertEqual(scenario.attention_action, AttentionAction.PRIVATE_SURFACE)
        self.assertEqual(scenario.attention_surface, "watch")
        self.assertNotEqual(scenario.attention_surface, "room_speaker")
        self.assertEqual(scenario.safety_violations, ())

    def test_habit_proposal_does_not_write_memory_or_create_rule(self):
        scenario = _scenario("habit_proposal")

        self.assertEqual(scenario.judgment_action, JudgmentAction.PROPOSE_MEMORY)
        self.assertEqual(scenario.recommendation, "propose_saving_preference")
        self.assertEqual(scenario.safety_violations, ())

    def test_learning_creates_bounded_pattern_from_counts_only(self):
        patterns = DeterministicLearning().evaluate(
            (
                Signal(
                    kind="repeated_night_mode",
                    confidence=ConfidenceBand.MEDIUM,
                    freshness=Freshness.FRESH,
                    provenance=EvidenceOrigin.INFERRED.value,
                    origin=EvidenceOrigin.INFERRED,
                    observation_count=5,
                    safe_explanation="Observed Night Mode repeatedly.",
                ),
            )
        )

        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].pattern_id, "night_mode")
        self.assertEqual(patterns[0].confidence, ConfidenceBand.HIGH)

    def test_memory_is_seeded_and_read_only(self):
        memory = SeededMemory(
            (
                MemoryPreference("minimize_interruptions", "deep_focus", True, "Approved."),
                MemoryPreference("unapproved", "ignored", False, "Not approved."),
            )
        )

        self.assertIsNotNone(memory.find("minimize_interruptions"))
        self.assertIsNone(memory.find("unapproved"))
        self.assertEqual(len(memory.preferences), 1)

    def test_report_contains_deterministic_metrics_and_explanations(self):
        report = CognitiveBenchmarkRunner(build_phase1_scenarios()).run()

        for scenario in report.scenarios:
            with self.subTest(scenario=scenario.scenario_id):
                self.assertIn("scenario_pass", scenario.deterministic_metrics)
                self.assertIn("recommendation_correctness", scenario.deterministic_metrics)
                self.assertIn("attention_correctness", scenario.deterministic_metrics)
                self.assertIn("no_execution_invariant", scenario.deterministic_metrics)
                self.assertTrue(scenario.explanation)

    def test_cognitive_package_does_not_import_execution_boundaries(self):
        forbidden_modules = {
            "jarvis_core.runtime",
            "jarvis_core.planner",
            "jarvis_core.drivers",
            "jarvis_core.device_state",
            "jarvis_core.api",
            "jarvis_core.dashboard",
            "jarvis_core.ai",
            "jarvis_core.ai_cloud",
            "jarvis_core.voice",
        }

        for path in COGNITIVE_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = _imports(tree)
            with self.subTest(path=path.name):
                self.assertTrue(forbidden_modules.isdisjoint(imported), imported)

    def test_cognitive_package_contains_no_persistence_network_or_provider_hooks(self):
        forbidden_tokens = (
            "open(",
            "Path(",
            "write_text",
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "threading",
            "Gemini",
            "Groq",
            "Ollama",
        )

        for path in COGNITIVE_ROOT.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for token in forbidden_tokens:
                    self.assertNotIn(token, text)


def _scenario(scenario_id):
    report = CognitiveBenchmarkRunner(build_phase1_scenarios()).run()
    for scenario in report.scenarios:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise AssertionError(f"Missing scenario {scenario_id}")


def _imports(tree):
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


if __name__ == "__main__":
    unittest.main()
