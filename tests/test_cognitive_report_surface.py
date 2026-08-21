import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest

from jarvis_core.cognitive import CognitiveBenchmarkRunner, CognitiveReportRenderer, build_phase1_scenarios
from jarvis_core.cognitive.__main__ import main as cognitive_main


REPO_ROOT = Path(__file__).resolve().parents[1]
COGNITIVE_ROOT = REPO_ROOT / "jarvis_core" / "cognitive"
RENDERED_FORBIDDEN_TERMS = (
    "action queued",
    "action scheduled",
    "executed",
    "device changed",
    "notification sent",
    "rule created",
    "memory saved",
    "delegation granted",
)


class CognitiveReportSurfaceTests(unittest.TestCase):
    def test_text_report_is_deterministic_and_covers_all_scenarios(self):
        renderer = CognitiveReportRenderer()
        first = renderer.render_text(_report())
        second = renderer.render_text(_report())

        self.assertEqual(first, second)
        self.assertIn("JarvisOS Cognitive Report", first)
        self.assertIn("scenario_success_rate: 1.000", first)
        for name in (
            "Deep Focus",
            "Night Mode Suggestion",
            "Stale Device",
            "Explicit User Correction",
            "Private Notification",
            "Habit Proposal",
        ):
            self.assertIn(name, first)
        self.assertIn("safety_invariant_violations: none", first)

    def test_json_report_is_canonical_and_deterministic(self):
        renderer = CognitiveReportRenderer()
        first = renderer.render_json(_report())
        second = renderer.render_json(_report())

        self.assertEqual(first, second)
        self.assertEqual(first, json.dumps(json.loads(first), ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n")
        payload = json.loads(first)
        self.assertEqual(payload["benchmark_version"], "cognitive-phase1-deterministic-v1")
        self.assertTrue(payload["passed"])
        self.assertEqual([scenario["scenario_id"] for scenario in payload["scenarios"]], _scenario_ids())

    def test_report_language_avoids_execution_or_delivery_claims(self):
        renderer = CognitiveReportRenderer()
        rendered = renderer.render_text(_report()) + renderer.render_json(_report())
        lowered = rendered.lower()

        for term in RENDERED_FORBIDDEN_TERMS:
            with self.subTest(term=term):
                self.assertNotIn(term, lowered)

    def test_scenarios_remain_recommendation_only_in_rendered_surface(self):
        text = CognitiveReportRenderer().render_text(_report())

        self.assertIn("recommendation: defer_low_urgency_notification", text)
        self.assertIn("recommendation: suggest_night_mode", text)
        self.assertIn("recommendation: request_explicit_status_read", text)
        self.assertIn("recommendation: do_not_continue_focus_recommendation", text)
        self.assertIn("recommendation: surface_private_notification_privately", text)
        self.assertIn("recommendation: propose_saving_preference", text)
        self.assertIn("attention: private_surface on watch", text)

    def test_module_entry_point_renders_text_without_touching_main_cli(self):
        output = io.StringIO()

        with redirect_stdout(output):
            result = cognitive_main([])

        self.assertEqual(result, 0)
        self.assertIn("JarvisOS Cognitive Report", output.getvalue())
        self.assertIn("Deep Focus", output.getvalue())

    def test_module_entry_point_renders_json(self):
        output = io.StringIO()

        with redirect_stdout(output):
            result = cognitive_main(["--format", "json"])

        self.assertEqual(result, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["scenarios"][0]["scenario_id"], "deep_focus")

    def test_cognitive_report_surface_does_not_import_product_boundaries(self):
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

        for path in (COGNITIVE_ROOT / "reporting.py", COGNITIVE_ROOT / "__main__.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = _imports(tree)
            with self.subTest(path=path.name):
                self.assertTrue(forbidden_modules.isdisjoint(imported), imported)

    def test_cognitive_report_surface_contains_no_side_effect_hooks(self):
        forbidden_tokens = (
            "open(",
            "Path(",
            "write_text",
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "threading",
            "datetime",
            "time.",
            "random",
            "environ",
            "Gemini",
            "Groq",
            "Ollama",
        )

        for path in (COGNITIVE_ROOT / "reporting.py", COGNITIVE_ROOT / "__main__.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for token in forbidden_tokens:
                    self.assertNotIn(token, text)


def _report():
    return CognitiveBenchmarkRunner(build_phase1_scenarios()).run()


def _scenario_ids():
    return [scenario.scenario_id for scenario in _report().scenarios]


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
