import ast
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from jarvis_core.second_brain import (
    InMemoryKnowledgeRetriever,
    KnowledgeFreshness,
    KnowledgeKind,
    RetrievalStatus,
    SecondBrainReportRenderer,
    build_seed_knowledge,
    run_demo_queries,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SECOND_BRAIN_ROOT = REPO_ROOT / "jarvis_core" / "second_brain"


class SecondBrainRetrievalTests(unittest.TestCase):
    def test_seeded_knowledge_is_immutable_and_test_safe(self):
        item = build_seed_knowledge()[0]

        with self.assertRaises(FrozenInstanceError):
            item.summary = "changed"

        all_text = " ".join(_all_item_text())
        forbidden_sensitive_terms = (
            "credential",
            "password",
            "token",
            "heart rate",
            "hrv",
            "sleep score",
            "bank",
            "private message",
            "precise location",
            "biometric",
        )
        for term in forbidden_sensitive_terms:
            self.assertNotIn(term, all_text.lower())

    def test_exact_lookup_selects_current_item(self):
        result = InMemoryKnowledgeRetriever().retrieve("wearable_phase1_fake_completed_real_pending")

        self.assertEqual(result.status, RetrievalStatus.FOUND)
        self.assertEqual(result.selected_evidence.knowledge_id, "wearable_phase1_fake_completed_real_pending")
        self.assertEqual(result.freshness, KnowledgeFreshness.CURRENT)
        self.assertIn("real Pixel Watch validation remains a separate gate", result.answer)

    def test_keyword_lookup_answers_pixel_watch_without_claiming_hardware_completion(self):
        result = InMemoryKnowledgeRetriever().retrieve("Where did I leave the Pixel Watch work?")

        self.assertEqual(result.status, RetrievalStatus.FOUND)
        self.assertEqual(result.selected_evidence.knowledge_id, "wearable_phase1_fake_completed_real_pending")
        self.assertIn("fake/deterministic phase is completed", result.answer)
        self.assertIn("real Pixel Watch validation remains a separate gate", result.answer)
        self.assertNotIn("real Pixel Watch connectivity completed", result.answer)

    def test_mqtt_lookup_returns_conservative_status(self):
        result = InMemoryKnowledgeRetriever().retrieve("What did we decide about MQTT?")

        self.assertEqual(result.status, RetrievalStatus.FOUND)
        self.assertIn("loopback Mosquitto", result.answer)
        self.assertIn("ESP32 MQTT reference-node validation remains unresolved", result.answer)
        self.assertNotIn("ESP32 MQTT completed", result.answer)

    def test_approved_preference_lookup(self):
        result = InMemoryKnowledgeRetriever().retrieve("approved preference lookup")

        self.assertEqual(result.status, RetrievalStatus.FOUND)
        self.assertEqual(result.selected_evidence.kind, KnowledgeKind.APPROVED_PREFERENCE)
        self.assertIn("concise status updates", result.answer)

    def test_supersession_selects_current_item_and_retains_old_evidence(self):
        result = InMemoryKnowledgeRetriever().retrieve("wearable pixel watch phase 1")

        self.assertEqual(result.status, RetrievalStatus.FOUND)
        self.assertEqual(result.selected_evidence.knowledge_id, "wearable_phase1_fake_completed_real_pending")
        self.assertEqual(
            tuple(item.knowledge_id for item in result.superseded_evidence),
            ("wearable_phase1_pending_hardware",),
        )
        self.assertIn("not co-current", result.safe_explanation)

    def test_explicit_correction_outranks_prior_fact(self):
        result = InMemoryKnowledgeRetriever().retrieve("synthetic workspace color")

        self.assertEqual(result.status, RetrievalStatus.FOUND)
        self.assertEqual(result.selected_evidence.knowledge_id, "synthetic_workspace_correction")
        self.assertEqual(result.answer, "The synthetic workspace color is green.")
        self.assertEqual(tuple(item.knowledge_id for item in result.superseded_evidence), ("synthetic_workspace_old",))
        self.assertIn("Explicit correction", result.safe_explanation)

    def test_source_precedence_selects_current_project_state_and_exposes_conflict(self):
        result = InMemoryKnowledgeRetriever().retrieve("source precedence demo")

        self.assertEqual(result.status, RetrievalStatus.FOUND)
        self.assertEqual(result.selected_evidence.knowledge_id, "project_status_current_source")
        self.assertEqual(tuple(item.knowledge_id for item in result.conflicting_evidence), ("project_status_stale_note",))
        self.assertTrue(result.has_contradiction)

    def test_equal_strength_contradiction_refuses_to_invent_truth(self):
        result = InMemoryKnowledgeRetriever().retrieve("ambiguous fixture")

        self.assertEqual(result.status, RetrievalStatus.CONTRADICTED)
        self.assertIsNone(result.answer)
        self.assertIsNone(result.selected_evidence)
        self.assertEqual(
            tuple(item.knowledge_id for item in result.conflicting_evidence),
            ("ambiguous_source_a", "ambiguous_source_b"),
        )
        self.assertIn("refused to invent", result.safe_explanation)

    def test_unknown_query_returns_no_fabricated_answer(self):
        result = InMemoryKnowledgeRetriever().retrieve("unknown fact")

        self.assertEqual(result.status, RetrievalStatus.UNKNOWN)
        self.assertIsNone(result.answer)
        self.assertEqual(result.supporting_evidence, ())
        self.assertIn("No matching", result.safe_explanation)

    def test_retrieval_ordering_is_deterministic(self):
        retriever = InMemoryKnowledgeRetriever()

        first = run_demo_queries(retriever)
        second = run_demo_queries(retriever)

        self.assertEqual(first, second)

    def test_text_and_json_diagnostic_rendering_are_deterministic_and_safe(self):
        renderer = SecondBrainReportRenderer()
        results = run_demo_queries()

        first_text = renderer.render_text(results)
        second_text = renderer.render_text(results)
        first_json = renderer.render_json(results)
        second_json = renderer.render_json(results)

        self.assertEqual(first_text, second_text)
        self.assertEqual(first_json, second_json)
        self.assertIn("JarvisOS Second Brain Diagnostic Report", first_text)
        payload = json.loads(first_json)
        self.assertEqual(payload["mode"], "deterministic_in_memory")
        self.assertEqual(len(payload["results"]), 6)
        _assert_no_execution_language(self, first_text + first_json)

    def test_second_brain_package_does_not_import_execution_boundaries_or_connectors(self):
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
            "sqlite3",
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "threading",
        }

        for path in SECOND_BRAIN_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = _imports(tree)
            with self.subTest(path=path.name):
                self.assertTrue(forbidden_modules.isdisjoint(imported), imported)

    def test_second_brain_package_has_no_runtime_persistence_or_provider_hooks(self):
        forbidden_tokens = (
            "Command(",
            "handle_adapter_input",
            ".read(",
            ".apply(",
            "open(",
            "Path(",
            "write_text",
            "sqlite",
            "vector",
            "embedding",
            "requests",
            "urllib",
            "socket",
            "subprocess",
            "threading",
            "datetime",
            "random",
            "environ",
            "Notion",
            "Obsidian",
            "Google Drive",
            "Gemini",
            "Groq",
            "Ollama",
        )

        for path in SECOND_BRAIN_ROOT.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                for token in forbidden_tokens:
                    self.assertNotIn(token, text)


def _all_item_text():
    for item in build_seed_knowledge():
        yield " ".join(
            (
                item.knowledge_id,
                item.kind.value,
                item.topic,
                item.summary,
                item.source_type,
                item.source_reference,
                item.safe_explanation,
            )
        )


def _assert_no_execution_language(test_case, text):
    forbidden = (
        "action queued",
        "action scheduled",
        "executed",
        "device changed",
        "notification sent",
        "rule created",
        "memory saved",
        "delegation granted",
        "command:",
    )
    lowered = text.lower()
    for term in forbidden:
        test_case.assertNotIn(term, lowered)


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
