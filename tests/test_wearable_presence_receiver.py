import ast
import json
from pathlib import Path
import unittest

from jarvis_core.cognitive import (
    AttentionAction,
    CognitiveBenchmarkRunner,
    Freshness,
    JudgmentAction,
)
from jarvis_core.cognitive.models import ScenarioInput, Sensitivity
from jarvis_core.wearable import (
    DEFAULT_WEARABLE_ID,
    WearableConnectionState,
    WearablePresenceReceiver,
    build_wearable_presence_fixtures,
    presence_payload,
    wearable_projection_to_signal,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
WEARABLE_ROOT = REPO_ROOT / "jarvis_core" / "wearable"
FORBIDDEN_INFERENCES = (
    "user_present",
    "user_wearing_watch",
    "user_awake",
    "user_available",
    "user_authenticated",
    "user_health",
    "user_location",
)


class ManualClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class WearablePresenceReceiverTests(unittest.TestCase):
    def test_no_heartbeat_projects_unknown_low_confidence(self):
        receiver = WearablePresenceReceiver(clock=ManualClock())

        projection = receiver.projection()
        signal = wearable_projection_to_signal(projection)

        self.assertEqual(projection.connection_state, WearableConnectionState.UNKNOWN)
        self.assertEqual(projection.freshness, Freshness.STALE)
        self.assertEqual(signal.kind, "watch_unknown_or_stale")
        self.assertEqual(signal.sensitivity, Sensitivity.PERSONAL)
        _assert_no_forbidden_inference(self, projection.safe_explanation + signal.safe_explanation)

    def test_valid_heartbeat_projects_connected_fresh(self):
        clock = ManualClock()
        receiver = WearablePresenceReceiver(clock=clock)

        result = receiver.receive_payload(presence_payload())
        projection = receiver.projection()
        signal = wearable_projection_to_signal(projection)

        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "connected")
        self.assertEqual(projection.connection_state, WearableConnectionState.CONNECTED)
        self.assertEqual(projection.freshness, Freshness.FRESH)
        self.assertEqual(signal.kind, "watch_connected")
        self.assertIn("connection evidence only", projection.safe_explanation)
        _assert_no_forbidden_inference(self, projection.safe_explanation + signal.safe_explanation)

    def test_repeated_heartbeat_refreshes_freshness(self):
        clock = ManualClock()
        receiver = WearablePresenceReceiver(stale_timeout_seconds=10.0, clock=clock)

        receiver.receive_payload(presence_payload())
        clock.advance(9.0)
        receiver.receive_payload(presence_payload())
        clock.advance(9.0)

        self.assertEqual(receiver.projection().connection_state, WearableConnectionState.CONNECTED)
        self.assertEqual(receiver.projection().freshness, Freshness.FRESH)

    def test_heartbeat_timeout_projects_stale_without_user_absence_inference(self):
        clock = ManualClock()
        receiver = WearablePresenceReceiver(stale_timeout_seconds=10.0, clock=clock)
        receiver.receive_payload(presence_payload())

        clock.advance(10.1)
        projection = receiver.projection()
        signal = wearable_projection_to_signal(projection)

        self.assertEqual(projection.connection_state, WearableConnectionState.STALE)
        self.assertEqual(projection.freshness, Freshness.STALE)
        self.assertEqual(signal.kind, "watch_unknown_or_stale")
        _assert_no_forbidden_inference(self, projection.safe_explanation + signal.safe_explanation)

    def test_explicit_disconnect_projects_disconnected_fresh(self):
        clock = ManualClock()
        receiver = WearablePresenceReceiver(clock=clock)
        receiver.receive_payload(presence_payload())

        result = receiver.receive_payload(presence_payload(state="disconnected"))
        projection = receiver.projection()
        signal = wearable_projection_to_signal(projection)

        self.assertTrue(result.accepted)
        self.assertEqual(projection.connection_state, WearableConnectionState.DISCONNECTED)
        self.assertEqual(projection.freshness, Freshness.FRESH)
        self.assertEqual(signal.kind, "watch_unavailable")
        _assert_no_forbidden_inference(self, projection.safe_explanation + signal.safe_explanation)

    def test_malformed_or_unsupported_payloads_are_rejected_without_state_change(self):
        clock = ManualClock()
        receiver = WearablePresenceReceiver(clock=clock)
        receiver.receive_payload(presence_payload())

        cases = (
            (b"{", "invalid_json"),
            (json.dumps(["not", "object"]).encode("utf-8"), "invalid_payload"),
            (json.dumps({"wearable_id": DEFAULT_WEARABLE_ID, "state": "connected", "extra": True}).encode("utf-8"), "unsupported_fields"),
            (presence_payload(wearable_id="other_watch"), "unsupported_wearable_id"),
            (presence_payload(state="worn"), "unsupported_state"),
        )
        for payload, reason in cases:
            with self.subTest(reason=reason):
                result = receiver.receive_payload(payload)
                self.assertFalse(result.accepted)
                self.assertEqual(result.reason, reason)
                self.assertEqual(receiver.projection().connection_state, WearableConnectionState.CONNECTED)

    def test_overlong_payload_is_rejected_without_state_change(self):
        receiver = WearablePresenceReceiver(max_payload_bytes=12, clock=ManualClock())

        result = receiver.receive_payload(b"0123456789abc")

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "payload_too_large")
        self.assertEqual(receiver.projection().connection_state, WearableConnectionState.UNKNOWN)

    def test_real_receiver_and_fake_fixture_share_projection_contract(self):
        receiver = WearablePresenceReceiver(clock=ManualClock())
        receiver.receive_payload(presence_payload())
        real_projection = receiver.projection()
        fake_projection = build_wearable_presence_fixtures()[0]

        self.assertEqual(real_projection.connection_state, fake_projection.connection_state)
        self.assertEqual(real_projection.capability_status, fake_projection.capability_status)
        self.assertEqual(real_projection.provenance, fake_projection.provenance)
        self.assertEqual(real_projection.sensitivity, fake_projection.sensitivity)
        self.assertEqual(wearable_projection_to_signal(real_projection).kind, wearable_projection_to_signal(fake_projection).kind)

    def test_real_projection_flows_to_diagnostic_cognition_without_execution(self):
        receiver = WearablePresenceReceiver(clock=ManualClock())
        receiver.receive_payload(presence_payload())
        signal = wearable_projection_to_signal(receiver.projection())

        report = CognitiveBenchmarkRunner(
            (
                ScenarioInput(
                    scenario_id="real_wearable_connected",
                    name="Real Wearable Connected",
                    signals=(signal,),
                    expected_judgment=JudgmentAction.SUGGEST,
                    expected_attention=AttentionAction.SURFACE,
                ),
            )
        ).run()

        scenario = report.scenarios[0]
        self.assertTrue(scenario.passed)
        self.assertEqual(scenario.recommendation, "note_watch_connection_signal_available")
        self.assertEqual(scenario.safety_violations, ())

    def test_wearable_receiver_modules_do_not_import_execution_or_product_boundaries(self):
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
            "requests",
            "urllib",
            "subprocess",
        }

        for path in WEARABLE_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = _imports(tree)
            with self.subTest(path=path.name):
                self.assertTrue(forbidden_modules.isdisjoint(imported), imported)

    def test_wearable_receiver_modules_contain_no_persistence_provider_or_execution_hooks(self):
        forbidden_tokens = (
            "Command(",
            "handle_adapter_input",
            ".apply(",
            "write_text",
            "Gemini",
            "Groq",
            "Ollama",
            "heart_rate",
            "biometric",
            "haptic",
            "microphone",
            "speaker",
        )

        for path in WEARABLE_ROOT.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                for token in forbidden_tokens:
                    self.assertNotIn(token, text)


def _assert_no_forbidden_inference(test_case: unittest.TestCase, text: str) -> None:
    lowered = text.lower()
    for inference in FORBIDDEN_INFERENCES:
        test_case.assertNotIn(inference, lowered)


def _imports(tree: ast.AST) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


if __name__ == "__main__":
    unittest.main()
