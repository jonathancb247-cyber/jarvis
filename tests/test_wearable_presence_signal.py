import ast
from dataclasses import FrozenInstanceError, fields
import json
from pathlib import Path
import unittest

from jarvis_core.cognitive import (
    AttentionAction,
    CognitiveBenchmarkRunner,
    CognitiveReportRenderer,
    EvidenceOrigin,
    Freshness,
    JudgmentAction,
)
from jarvis_core.cognitive.models import ScenarioInput, Sensitivity
from jarvis_core.wearable import (
    WearableCapabilityStatus,
    WearableConnectionState,
    WearablePresenceProjection,
    build_wearable_presence_fixtures,
    wearable_projection_to_signal,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
WEARABLE_ROOT = REPO_ROOT / "jarvis_core" / "wearable"
COGNITIVE_ROOT = REPO_ROOT / "jarvis_core" / "cognitive"
FORBIDDEN_INFERENCES = (
    "user_present",
    "user_wearing_watch",
    "user_awake",
    "user_available",
    "user_authenticated",
    "user_health",
    "user_location",
)


class WearablePresenceSignalTests(unittest.TestCase):
    def test_fake_fixtures_cover_connected_disconnected_unknown_and_stale(self):
        fixtures = build_wearable_presence_fixtures()

        self.assertEqual(
            tuple(fixture.connection_state for fixture in fixtures),
            (
                WearableConnectionState.CONNECTED,
                WearableConnectionState.DISCONNECTED,
                WearableConnectionState.UNKNOWN,
                WearableConnectionState.STALE,
            ),
        )
        self.assertEqual(fixtures[0].capability_status, WearableCapabilityStatus.SUPPORTED)
        self.assertEqual(fixtures[1].capability_status, WearableCapabilityStatus.UNAVAILABLE)
        self.assertEqual(fixtures[2].capability_status, WearableCapabilityStatus.UNKNOWN)
        self.assertEqual(fixtures[3].capability_status, WearableCapabilityStatus.PARTIALLY_SUPPORTED)

    def test_connected_projection_maps_to_watch_connected_without_identity_or_presence_inference(self):
        signal = wearable_projection_to_signal(build_wearable_presence_fixtures()[0])

        self.assertEqual(signal.kind, "watch_connected")
        self.assertEqual(signal.origin, EvidenceOrigin.WEARABLE)
        self.assertEqual(signal.provenance, "wearable")
        self.assertEqual(signal.freshness, Freshness.FRESH)
        self.assertEqual(signal.sensitivity, Sensitivity.PERSONAL)
        self.assertEqual(signal.user_scope, "primary_user")
        _assert_no_forbidden_inference(self, signal.kind)
        _assert_no_forbidden_inference(self, signal.safe_explanation)

    def test_disconnected_projection_maps_to_unavailable_without_user_absence_inference(self):
        signal = wearable_projection_to_signal(build_wearable_presence_fixtures()[1])

        self.assertEqual(signal.kind, "watch_unavailable")
        self.assertEqual(signal.origin, EvidenceOrigin.WEARABLE)
        self.assertEqual(signal.freshness, Freshness.FRESH)
        self.assertIn("unavailable", signal.safe_explanation)
        _assert_no_forbidden_inference(self, signal.safe_explanation)

    def test_unknown_and_stale_projections_map_to_low_confidence_degraded_evidence(self):
        for projection in build_wearable_presence_fixtures()[2:]:
            with self.subTest(state=projection.connection_state.value):
                signal = wearable_projection_to_signal(projection)

                self.assertEqual(signal.kind, "watch_unknown_or_stale")
                self.assertEqual(signal.freshness, Freshness.STALE)
                self.assertEqual(signal.origin, EvidenceOrigin.WEARABLE)
                self.assertIn("reduced", signal.safe_explanation)
                _assert_no_forbidden_inference(self, signal.safe_explanation)

    def test_context_judgment_and_attention_for_connected_are_diagnostic_only(self):
        scenario = _run_wearable_scenario(
            "wearable_connected",
            "Wearable Connected",
            build_wearable_presence_fixtures()[0],
            JudgmentAction.SUGGEST,
            AttentionAction.SURFACE,
        )

        self.assertTrue(scenario.passed)
        self.assertEqual(scenario.recommendation, "note_watch_connection_signal_available")
        self.assertEqual(scenario.attention_surface, "dashboard")
        self.assertIn("context evidence only", scenario.explanation)
        self.assertEqual(scenario.safety_violations, ())

    def test_context_judgment_and_attention_for_degraded_states_reduce_confidence_only(self):
        for projection in build_wearable_presence_fixtures()[1:]:
            with self.subTest(state=projection.connection_state.value):
                scenario = _run_wearable_scenario(
                    f"wearable_{projection.connection_state.value}",
                    f"Wearable {projection.connection_state.value.title()}",
                    projection,
                    JudgmentAction.CLARIFY,
                    AttentionAction.SURFACE,
                )

                self.assertTrue(scenario.passed)
                self.assertEqual(scenario.recommendation, "note_wearable_context_confidence_reduced")
                self.assertIn("no user context should be inferred", scenario.explanation)
                self.assertEqual(scenario.safety_violations, ())

    def test_report_surface_renders_wearable_scenarios_without_execution_claims(self):
        renderer = CognitiveReportRenderer()
        report = CognitiveBenchmarkRunner(_wearable_scenarios()).run()
        first_text = renderer.render_text(report)
        second_text = renderer.render_text(report)
        first_json = renderer.render_json(report)
        second_json = renderer.render_json(report)

        self.assertEqual(first_text, second_text)
        self.assertEqual(first_json, second_json)
        self.assertIn("Wearable Connected", first_text)
        self.assertIn("note_watch_connection_signal_available", first_text)
        self.assertEqual(
            [scenario["scenario_id"] for scenario in json.loads(first_json)["scenarios"]],
            ["wearable_connected", "wearable_disconnected", "wearable_unknown", "wearable_stale"],
        )
        _assert_no_forbidden_inference(self, first_text + first_json)

    def test_projection_is_frozen_and_detached(self):
        projection = build_wearable_presence_fixtures()[0]

        with self.assertRaises(FrozenInstanceError):
            projection.wearable_id = "changed"

    def test_projection_has_no_sensitive_wearable_data_fields(self):
        field_names = {field.name for field in fields(WearablePresenceProjection)}

        self.assertTrue(
            {
                "wearable_id",
                "connection_state",
                "capability_status",
                "provenance",
                "freshness",
                "confidence",
                "sensitivity",
                "user_scope",
                "safe_explanation",
            }.issubset(field_names)
        )
        self.assertTrue(
            {
                "heart_rate",
                "hr",
                "hrv",
                "sleep",
                "activity",
                "exercise",
                "location",
                "biometric",
                "wrist_presence",
            }.isdisjoint(field_names)
        )

    def test_fixture_and_mapping_results_are_deterministic(self):
        first = [wearable_projection_to_signal(projection) for projection in build_wearable_presence_fixtures()]
        second = [wearable_projection_to_signal(projection) for projection in build_wearable_presence_fixtures()]

        self.assertEqual(first, second)

    def test_wearable_package_does_not_import_execution_or_product_boundaries(self):
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
            "socket",
            "subprocess",
        }

        for path in WEARABLE_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = _imports(tree)
            with self.subTest(path=path.name):
                self.assertTrue(forbidden_modules.isdisjoint(imported), imported)

    def test_wearable_package_has_no_forbidden_runtime_hooks(self):
        forbidden_tokens = (
            "Command(",
            "handle_adapter_input",
            ".apply(",
            "open(",
            "write_text",
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "threading",
            "datetime",
            "random",
            "environ",
            "adb",
            "android",
            "haptic",
            "microphone",
            "speaker",
            "Gemini",
            "Groq",
            "Ollama",
        )

        for path in WEARABLE_ROOT.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                for token in forbidden_tokens:
                    self.assertNotIn(token, text)


def _wearable_scenarios():
    scenarios = []
    for projection in build_wearable_presence_fixtures():
        connected = projection.connection_state is WearableConnectionState.CONNECTED
        scenarios.append(
            ScenarioInput(
                scenario_id=f"wearable_{projection.connection_state.value}",
                name=f"Wearable {projection.connection_state.value.title()}",
                signals=(wearable_projection_to_signal(projection),),
                expected_judgment=JudgmentAction.SUGGEST if connected else JudgmentAction.CLARIFY,
                expected_attention=AttentionAction.SURFACE,
            )
        )
    return tuple(scenarios)


def _run_wearable_scenario(scenario_id, name, projection, expected_judgment, expected_attention):
    return CognitiveBenchmarkRunner(
        (
            ScenarioInput(
                scenario_id=scenario_id,
                name=name,
                signals=(wearable_projection_to_signal(projection),),
                expected_judgment=expected_judgment,
                expected_attention=expected_attention,
            ),
        )
    ).run().scenarios[0]


def _assert_no_forbidden_inference(test_case, text):
    lowered = text.lower()
    for inference in FORBIDDEN_INFERENCES:
        test_case.assertNotIn(inference, lowered)


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
