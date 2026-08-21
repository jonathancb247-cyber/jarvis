import ast
import copy
import json
from pathlib import Path
import unittest

from jarvis_core.cognitive import (
    AttentionAction,
    CognitiveBenchmarkRunner,
    CognitiveReportRenderer,
    ConfidenceBand,
    DeviceStateProjectionStatus,
    DeviceStateSemanticProjection,
    EvidenceOrigin,
    Freshness,
    JudgmentAction,
    build_phase1_scenarios,
    device_state_projection_to_signal,
)
from jarvis_core.cognitive.models import ScenarioInput


REPO_ROOT = Path(__file__).resolve().parents[1]
COGNITIVE_ROOT = REPO_ROOT / "jarvis_core" / "cognitive"


class CognitiveDeviceStateSignalTests(unittest.TestCase):
    def test_known_current_projection_maps_to_fresh_evidence_without_refresh_recommendation(self):
        signal = device_state_projection_to_signal(
            DeviceStateSemanticProjection.from_mapping(
                device_id="lamp_1",
                status=DeviceStateProjectionStatus.KNOWN,
                is_current=True,
                safe_properties={"power": False},
            )
        )

        self.assertEqual(signal.kind, "current_device_state")
        self.assertEqual(signal.origin, EvidenceOrigin.DEVICE_STATE)
        self.assertEqual(signal.freshness, Freshness.FRESH)
        self.assertEqual(signal.confidence, ConfidenceBand.HIGH)
        self.assertNotIn("read", signal.safe_explanation.lower())
        self.assertNotIn("refresh", signal.safe_explanation.lower())

    def test_stale_projection_maps_to_stale_evidence_with_safe_property_summary(self):
        signal = device_state_projection_to_signal(
            DeviceStateSemanticProjection.from_mapping(
                device_id="lamp_1",
                status="stale",
                is_current=False,
                safe_properties={"power": False},
            )
        )

        self.assertEqual(signal.kind, "stale_device_state")
        self.assertEqual(signal.freshness, Freshness.STALE)
        self.assertIn("not current", signal.safe_explanation)
        self.assertIn("power=False", signal.safe_explanation)

    def test_unknown_projection_maps_to_insufficient_evidence_without_fabricated_properties(self):
        signal = device_state_projection_to_signal(
            DeviceStateSemanticProjection.from_mapping(
                device_id="lamp_1",
                status="unknown",
                is_current=False,
                safe_properties={"power": True},
            )
        )

        self.assertEqual(signal.kind, "unknown_device_state")
        self.assertEqual(signal.freshness, Freshness.STALE)
        self.assertEqual(signal.confidence, ConfidenceBand.LOW)
        self.assertNotIn("power", signal.safe_explanation)
        self.assertIn("Insufficient", signal.safe_explanation)

    def test_projection_normalizes_safe_properties_without_shared_mutable_reference(self):
        properties = {"power": False, "socket_error": "timed out", "base_url": "http://private", "mode": "lamp"}
        original = copy.deepcopy(properties)
        projection = DeviceStateSemanticProjection.from_mapping(
            device_id="lamp_1",
            status="stale",
            is_current=False,
            safe_properties=properties,
        )
        properties["power"] = True

        self.assertEqual(original, {"power": False, "socket_error": "timed out", "base_url": "http://private", "mode": "lamp"})
        self.assertEqual(projection.safe_properties[0].key, "mode")
        self.assertEqual(projection.safe_properties[1].key, "power")
        self.assertEqual(projection.safe_properties[1].value, False)
        self.assertEqual(len(projection.safe_properties), 2)

    def test_projection_bounds_properties_and_string_values(self):
        properties = {f"safe_{index}": "x" * 120 for index in range(12)}
        projection = DeviceStateSemanticProjection.from_mapping(
            device_id="lamp_1",
            status="stale",
            is_current=False,
            safe_properties=properties,
        )

        self.assertEqual(len(projection.safe_properties), 8)
        self.assertTrue(all(isinstance(property.value, str) for property in projection.safe_properties))
        self.assertTrue(all(len(property.value) == 80 for property in projection.safe_properties))

    def test_stale_device_state_scenario_recommends_explicit_read_only(self):
        scenario = _scenario("stale_device")

        self.assertEqual(scenario.judgment_action, JudgmentAction.CLARIFY)
        self.assertEqual(scenario.attention_action, AttentionAction.SURFACE)
        self.assertEqual(scenario.recommendation, "request_explicit_status_read")
        self.assertIn("fresh read should be requested", scenario.explanation)
        self.assertEqual(scenario.safety_violations, ())

    def test_known_current_device_state_scenario_does_not_request_refresh(self):
        scenario = _run_device_state_scenario(
            scenario_id="current_device_state",
            name="Current DeviceState",
            signal=device_state_projection_to_signal(
                DeviceStateSemanticProjection.from_mapping(
                    device_id="lamp_1",
                    status="known",
                    is_current=True,
                    safe_properties={"power": False},
                )
            ),
            expected_judgment=JudgmentAction.ABSTAIN,
            expected_attention=AttentionAction.SILENCE,
        )

        self.assertEqual(scenario.judgment_action, JudgmentAction.ABSTAIN)
        self.assertEqual(scenario.attention_action, AttentionAction.SILENCE)
        self.assertEqual(scenario.recommendation, "no_recommendation")
        self.assertNotIn("read", scenario.recommendation)
        self.assertNotIn("refresh", scenario.recommendation)

    def test_unknown_device_state_scenario_clarifies_without_physical_assumption(self):
        scenario = _run_device_state_scenario(
            scenario_id="unknown_device_state",
            name="Unknown DeviceState",
            signal=device_state_projection_to_signal(
                DeviceStateSemanticProjection.from_mapping(
                    device_id="lamp_1",
                    status="unknown",
                    is_current=False,
                    safe_properties={},
                )
            ),
            expected_judgment=JudgmentAction.CLARIFY,
            expected_attention=AttentionAction.SURFACE,
        )

        self.assertEqual(scenario.judgment_action, JudgmentAction.CLARIFY)
        self.assertEqual(scenario.attention_action, AttentionAction.SURFACE)
        self.assertEqual(scenario.recommendation, "request_device_status_evidence")
        self.assertIn("should not be assumed", scenario.explanation)
        self.assertEqual(scenario.safety_violations, ())

    def test_report_surface_remains_deterministic_with_device_state_scenarios(self):
        renderer = CognitiveReportRenderer()
        first_text = renderer.render_text(_report())
        second_text = renderer.render_text(_report())
        first_json = renderer.render_json(_report())
        second_json = renderer.render_json(_report())

        self.assertEqual(first_text, second_text)
        self.assertEqual(first_json, second_json)
        payload = json.loads(first_json)
        self.assertEqual(len(payload["scenarios"]), 6)
        self.assertIn("Stale Device", [scenario["scenario_name"] for scenario in payload["scenarios"]])

    def test_existing_phase1_scenarios_remain_present_and_passing(self):
        report = _report()
        scenarios = {scenario.scenario_id: scenario for scenario in report.scenarios}

        for scenario_id in (
            "deep_focus",
            "night_mode_suggestion",
            "stale_device",
            "explicit_user_correction",
            "private_notification",
            "habit_proposal",
        ):
            with self.subTest(scenario=scenario_id):
                self.assertIn(scenario_id, scenarios)
                self.assertTrue(scenarios[scenario_id].passed)

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
            "jarvis_core.state_store",
        }

        for path in COGNITIVE_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = _imports(tree)
            with self.subTest(path=path.name):
                self.assertTrue(forbidden_modules.isdisjoint(imported), imported)

    def test_cognitive_package_contains_no_execution_or_side_effect_hooks(self):
        forbidden_tokens = (
            "Command(",
            "handle_adapter_input",
            ".read(",
            ".apply(",
            "open(",
            "Path(",
            "write_text",
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "threading",
            "datetime",
            "random",
            "environ",
            "Gemini",
            "Groq",
            "Ollama",
        )

        for path in COGNITIVE_ROOT.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                for token in forbidden_tokens:
                    self.assertNotIn(token, text)


def _report():
    return CognitiveBenchmarkRunner(build_phase1_scenarios()).run()


def _scenario(scenario_id):
    for scenario in _report().scenarios:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise AssertionError(f"Missing scenario {scenario_id}")


def _run_device_state_scenario(
    *,
    scenario_id,
    name,
    signal,
    expected_judgment,
    expected_attention,
):
    report = CognitiveBenchmarkRunner(
        (
            ScenarioInput(
                scenario_id=scenario_id,
                name=name,
                signals=(signal,),
                expected_judgment=expected_judgment,
                expected_attention=expected_attention,
            ),
        )
    ).run()
    return report.scenarios[0]


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
