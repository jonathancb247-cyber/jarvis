import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from jarvis_core.second_brain import (
    InMemoryKnowledgeRetriever,
    KnowledgeFreshness,
    KnowledgeItem,
    KnowledgeSensitivity,
    RetrievalStatus,
    SECOND_BRAIN_SCHEMA_VERSION,
    SQLiteKnowledgeRepository,
    SecondBrainStorageError,
    build_seed_knowledge,
    seed_repository,
)
from jarvis_core.second_brain.__main__ import main as second_brain_main
from jarvis_core.second_brain.retrieval import build_demo_queries


class SQLiteKnowledgeRepositoryTests(unittest.TestCase):
    def test_initialize_records_schema_version_without_seeded_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "second-brain.sqlite"
            self.assertFalse(db_path.exists())

            repository = SQLiteKnowledgeRepository(db_path)
            repository.initialize()

            self.assertTrue(db_path.exists())
            self.assertEqual(repository.schema_version(), SECOND_BRAIN_SCHEMA_VERSION)
            self.assertEqual(repository.health(), {"schema_version": 1, "item_count": 0})

    def test_insert_get_list_and_reload_are_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "second-brain.sqlite"
            repository = SQLiteKnowledgeRepository(db_path)
            repository.initialize()
            seed_repository(repository, build_seed_knowledge())

            reloaded = SQLiteKnowledgeRepository(db_path)
            reloaded.initialize()

            self.assertEqual(reloaded.list(), build_seed_knowledge())
            self.assertEqual(
                reloaded.get("wearable_phase1_fake_completed_real_pending"),
                build_seed_knowledge()[1],
            )

    def test_duplicate_insert_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _seeded_repository(directory)
            item = build_seed_knowledge()[0]

            with self.assertRaisesRegex(SecondBrainStorageError, "duplicate_knowledge_id"):
                repository.insert(item)

            self.assertEqual(repository.get(item.knowledge_id), item)

    def test_sqlite_retrieval_matches_phase1_results(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _seeded_repository(directory)
            sqlite_retriever = InMemoryKnowledgeRetriever(repository.list())
            memory_retriever = InMemoryKnowledgeRetriever()

            for query in build_demo_queries():
                with self.subTest(query=query):
                    sqlite_result = sqlite_retriever.retrieve(query)
                    memory_result = memory_retriever.retrieve(query)
                    self.assertEqual(sqlite_result.status, memory_result.status)
                    self.assertEqual(sqlite_result.answer, memory_result.answer)
                    self.assertEqual(sqlite_result.safe_explanation, memory_result.safe_explanation)
                    self.assertEqual(_ids(sqlite_result.supporting_evidence), _ids(memory_result.supporting_evidence))
                    self.assertEqual(_ids(sqlite_result.conflicting_evidence), _ids(memory_result.conflicting_evidence))
                    self.assertEqual(_ids(sqlite_result.superseded_evidence), _ids(memory_result.superseded_evidence))

    def test_correction_supersession_is_atomic_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _seeded_repository(directory)
            correction = _ordinary_item(
                "phase2_workspace_correction",
                topic="synthetic workspace color",
                summary="The synthetic workspace color is blue.",
                source_type="explicit_user_correction",
                source_reference="synthetic_phase2_correction",
            )

            repository.correct("synthetic_workspace_correction", correction)
            reloaded = SQLiteKnowledgeRepository(Path(directory) / "second-brain.sqlite")
            reloaded.initialize()

            prior = reloaded.get("synthetic_workspace_correction")
            stored_correction = reloaded.get("phase2_workspace_correction")
            result = InMemoryKnowledgeRetriever(reloaded.list()).retrieve("synthetic workspace color")
            self.assertEqual(prior.freshness, KnowledgeFreshness.SUPERSEDED)
            self.assertEqual(prior.superseded_by, ("phase2_workspace_correction",))
            self.assertEqual(stored_correction.supersedes, ("synthetic_workspace_correction",))
            self.assertEqual(result.status, RetrievalStatus.FOUND)
            self.assertEqual(result.selected_evidence.knowledge_id, "phase2_workspace_correction")

    def test_failed_correction_rolls_back_prior_supersession(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _seeded_repository(directory)
            duplicate = replace(
                build_seed_knowledge()[1],
                supersedes=("synthetic_workspace_correction",),
            )

            with self.assertRaisesRegex(SecondBrainStorageError, "duplicate_knowledge_id"):
                repository.correct("synthetic_workspace_correction", duplicate)

            prior = repository.get("synthetic_workspace_correction")
            self.assertEqual(prior.freshness, KnowledgeFreshness.CURRENT)
            self.assertEqual(prior.superseded_by, ())

    def test_logical_delete_hides_item_but_keeps_admin_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _seeded_repository(directory)

            self.assertTrue(repository.logical_delete("preference_brief_status"))

            self.assertIsNone(repository.get("preference_brief_status"))
            self.assertIsNotNone(repository.get("preference_brief_status", include_deleted=True))
            self.assertNotIn("preference_brief_status", _ids(repository.list()))
            self.assertIn("preference_brief_status", _ids(repository.list(include_deleted=True)))

    def test_hard_purge_removes_item_after_reopen_without_secure_erase_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _seeded_repository(directory)
            self.assertTrue(repository.hard_purge("preference_brief_status"))

            reloaded = SQLiteKnowledgeRepository(Path(directory) / "second-brain.sqlite")
            reloaded.initialize()

            self.assertIsNone(reloaded.get("preference_brief_status", include_deleted=True))

    def test_user_scope_filtering_does_not_cross_primary_guest_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _seeded_repository(directory)
            repository.insert(_ordinary_item("guest_note", user_scope="guest_session"))
            repository.insert(_ordinary_item("unknown_note", user_scope="unknown"))

            primary = _ids(repository.list(user_scope="primary_user"))
            guest = _ids(repository.list(user_scope="guest_session"))
            unknown = _ids(repository.list(user_scope="unknown"))

            self.assertIn("preference_brief_status", primary)
            self.assertNotIn("preference_brief_status", guest)
            self.assertNotIn("preference_brief_status", unknown)
            self.assertEqual(guest, ("guest_note",))
            self.assertEqual(unknown, ("unknown_note",))

    def test_rejects_sensitive_or_blocked_fixture_content(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _empty_repository(directory)
            sensitive = replace(_ordinary_item("sensitive_fixture"), sensitivity=KnowledgeSensitivity.SENSITIVE)
            blocked = _ordinary_item("blocked_fixture", summary="Synthetic private message fixture.")

            with self.assertRaisesRegex(SecondBrainStorageError, "unsupported_sensitivity"):
                repository.insert(sensitive)
            with self.assertRaisesRegex(SecondBrainStorageError, "unsupported_sensitivity"):
                repository.insert(blocked)

    def test_malformed_enum_row_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _empty_repository(directory)
            _insert_raw_row(Path(directory) / "second-brain.sqlite", kind="not_a_kind")

            with self.assertRaisesRegex(SecondBrainStorageError, "storage_corrupt"):
                repository.list()

    def test_unsupported_schema_version_fails_without_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = _empty_repository(directory)
            db_path = Path(directory) / "second-brain.sqlite"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "UPDATE second_brain_metadata SET value = ? WHERE key = ?",
                    ("999", "schema_version"),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(SecondBrainStorageError, "schema_version_unsupported"):
                SQLiteKnowledgeRepository(db_path).initialize()

    def test_corrupted_database_file_fails_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "second-brain.sqlite"
            db_path.write_bytes(b"not sqlite")

            with self.assertRaisesRegex(SecondBrainStorageError, "storage_corrupt"):
                SQLiteKnowledgeRepository(db_path).initialize()

    def test_cli_sqlite_mode_is_explicit_and_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "second-brain.sqlite"
            first_output = io.StringIO()
            second_output = io.StringIO()

            with contextlib.redirect_stdout(first_output):
                first_code = second_brain_main(["--storage", "sqlite", "--db", str(db_path), "--seed-fixtures"])
            with contextlib.redirect_stdout(second_output):
                second_code = second_brain_main(["--storage", "sqlite", "--db", str(db_path), "--format", "json"])

            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            payload = json.loads(second_output.getvalue())
            self.assertEqual(payload["mode"], "deterministic_in_memory")
            self.assertEqual(len(payload["results"]), 6)

    def test_cli_reports_duplicate_seed_without_raw_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "second-brain.sqlite"
            stderr = io.StringIO()

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(second_brain_main(["--storage", "sqlite", "--db", str(db_path), "--seed-fixtures"]), 0)
            with contextlib.redirect_stderr(stderr):
                code = second_brain_main(["--storage", "sqlite", "--db", str(db_path), "--seed-fixtures"])

            self.assertEqual(code, 1)
            self.assertEqual(stderr.getvalue().strip(), "Second Brain storage error: duplicate_knowledge_id")


def _empty_repository(directory: str) -> SQLiteKnowledgeRepository:
    repository = SQLiteKnowledgeRepository(Path(directory) / "second-brain.sqlite")
    repository.initialize()
    return repository


def _seeded_repository(directory: str) -> SQLiteKnowledgeRepository:
    repository = _empty_repository(directory)
    seed_repository(repository, build_seed_knowledge())
    return repository


def _ordinary_item(
    knowledge_id: str,
    *,
    topic: str = "synthetic phase 2 fixture",
    summary: str = "Synthetic ordinary fixture for SQLite persistence.",
    source_type: str = "synthetic_fixture",
    source_reference: str = "phase2_fixture",
    user_scope: str = "system",
) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        kind=build_seed_knowledge()[0].kind,
        topic=topic,
        summary=summary,
        source_type=source_type,
        source_reference=source_reference,
        freshness=KnowledgeFreshness.CURRENT,
        confidence=build_seed_knowledge()[0].confidence,
        origin=build_seed_knowledge()[0].origin,
        sensitivity=KnowledgeSensitivity.ORDINARY,
        user_scope=user_scope,
        captured_at="2026-08-24T00:00:00Z",
        safe_explanation="Synthetic ordinary fixture only.",
    )


def _insert_raw_row(db_path: Path, *, kind: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            INSERT INTO knowledge_items (
                knowledge_id, kind, topic, summary, source_type, source_reference,
                freshness, confidence, origin, sensitivity, user_scope, captured_at,
                supersedes_json, superseded_by_json, contradicted_by_json,
                safe_explanation, deleted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                "malformed",
                kind,
                "malformed fixture",
                "Malformed row.",
                "synthetic_fixture",
                "malformed",
                "current",
                "high",
                "explicit",
                "ordinary",
                "system",
                "2026-08-24T00:00:00Z",
                "[]",
                "[]",
                "[]",
                "Malformed row fixture.",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _ids(items):
    return tuple(item.knowledge_id for item in items)


if __name__ == "__main__":
    unittest.main()
