import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from jarvis_core.second_brain.index import SQLiteSourceIndex, SourceIndexError
from jarvis_core.second_brain.github_sources import (
    GitHubFileSnapshot,
    GitHubSourceAdapter,
    GitHubSourceError,
)
from jarvis_core.second_brain.models import (
    KnowledgeConfidence,
    KnowledgeFreshness,
    KnowledgeSensitivity,
)
from jarvis_core.second_brain.source_retrieval import (
    SourceHybridRetriever,
    SourceReportRenderer,
)
from jarvis_core.second_brain.sources import (
    LocalMarkdownSourceAdapter,
    SourceAuthority,
    SourceRecord,
    SourceRetrievalStatus,
    SourceType,
    build_source_fixture_records,
    parse_markdown_source,
    render_markdown_source,
    write_source_fixture_markdown,
)


class SecondBrainSourceIndexTests(unittest.TestCase):
    def test_fixture_source_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = write_source_fixture_markdown(temp)

            record = parse_markdown_source(paths[0])

        self.assertIsInstance(record, SourceRecord)
        self.assertEqual(record.sensitivity, KnowledgeSensitivity.ORDINARY)
        self.assertEqual(record.source_type, SourceType.LOCAL_MARKDOWN)

    def test_malformed_source_input_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.md"
            path.write_text("missing front matter", encoding="utf-8")

            with self.assertRaises(ValueError):
                parse_markdown_source(path)

    def test_deterministic_index_persists_and_reopens(self):
        with tempfile.TemporaryDirectory() as temp:
            source_dir, db_path = _source_and_db(temp)
            write_source_fixture_markdown(source_dir)
            index = _initialized_index(db_path)
            summary = index.refresh(LocalMarkdownSourceAdapter(source_dir))
            first = index.list()
            reopened = _initialized_index(db_path).list()

        self.assertEqual(summary["inserted"], len(build_source_fixture_records()))
        self.assertEqual(first, reopened)

    def test_duplicate_prevention_unchanged_source(self):
        with tempfile.TemporaryDirectory() as temp:
            source_dir, db_path = _source_and_db(temp)
            write_source_fixture_markdown(source_dir)
            index = _initialized_index(db_path)
            index.refresh(LocalMarkdownSourceAdapter(source_dir))
            summary = index.refresh(LocalMarkdownSourceAdapter(source_dir))

        self.assertEqual(summary["unchanged"], len(build_source_fixture_records()))
        self.assertEqual(summary["inserted"], 0)

    def test_source_update_reindex_supersedes_old_version(self):
        with tempfile.TemporaryDirectory() as temp:
            source_dir, db_path = _source_and_db(temp)
            write_source_fixture_markdown(source_dir)
            index = _initialized_index(db_path)
            index.refresh(LocalMarkdownSourceAdapter(source_dir))
            old = _document_for_source(index, "mqtt_status_current")
            _write_record(
                source_dir,
                _record("mqtt_status_current", "MQTT physical ESP32 validation is still a future gate."),
            )

            summary = index.refresh(LocalMarkdownSourceAdapter(source_dir))
            all_docs = index.list(include_deleted=True)
            new = _document_for_source(index, "mqtt_status_current")

        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(summary["superseded"], 1)
        self.assertNotEqual(old.document_id, new.document_id)
        self.assertEqual(new.supersedes, (old.document_id,))
        self.assertIn(
            old.document_id,
            [document.document_id for document in all_docs if document.freshness is KnowledgeFreshness.SUPERSEDED],
        )

    def test_source_deletion_refresh_stops_current_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            source_dir, db_path = _source_and_db(temp)
            write_source_fixture_markdown(source_dir)
            index = _initialized_index(db_path)
            index.refresh(LocalMarkdownSourceAdapter(source_dir))
            before = SourceHybridRetriever(index.list()).retrieve("Second Brain durable storage")
            for path in Path(source_dir).glob("*second_brain_storage_adr.md"):
                path.unlink()
            summary = index.refresh(LocalMarkdownSourceAdapter(source_dir))
            after = SourceHybridRetriever(index.list()).retrieve("Second Brain durable storage")
            stale = [
                document
                for document in index.list(include_deleted=True)
                if document.source_id == "second_brain_storage_adr"
            ][0]

        self.assertEqual(before.status, SourceRetrievalStatus.FOUND)
        self.assertEqual(summary["deleted"], 1)
        self.assertEqual(after.status, SourceRetrievalStatus.UNKNOWN)
        self.assertTrue(stale.deleted)
        self.assertEqual(stale.freshness, KnowledgeFreshness.STALE)

    def test_refresh_deletion_is_scoped_to_adapter_source_set(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            first_dir = base / "first"
            second_dir = base / "second"
            db_path = base / "source-index.sqlite"
            _write_record(first_dir, _record("first_doc", "Scoped deletion first source set."))
            _write_record(second_dir, _record("second_doc", "Scoped deletion second source set."))
            index = _initialized_index(db_path)
            index.refresh(LocalMarkdownSourceAdapter(first_dir))
            index.refresh(LocalMarkdownSourceAdapter(second_dir))
            (first_dir / "first_doc.md").unlink()

            summary = index.refresh(LocalMarkdownSourceAdapter(first_dir))
            active_source_ids = {document.source_id for document in index.list()}

        self.assertEqual(summary["deleted"], 1)
        self.assertNotIn("first_doc", active_source_ids)
        self.assertIn("second_doc", active_source_ids)

    def test_invalid_source_directory_fails_with_bounded_error(self):
        with tempfile.TemporaryDirectory() as temp:
            index = _initialized_index(Path(temp) / "source-index.sqlite")

            with self.assertRaises(SourceIndexError) as raised:
                index.refresh(LocalMarkdownSourceAdapter(Path(temp) / "missing"))

        self.assertEqual(raised.exception.code, "source_adapter_failed")

    def test_too_large_source_file_fails_with_bounded_error(self):
        with tempfile.TemporaryDirectory() as temp:
            source_dir, db_path = _source_and_db(temp)
            source_dir.mkdir(parents=True)
            (source_dir / "large.md").write_text("x" * (65 * 1024), encoding="utf-8")
            index = _initialized_index(db_path)

            with self.assertRaises(SourceIndexError) as raised:
                index.refresh(LocalMarkdownSourceAdapter(source_dir))

        self.assertEqual(raised.exception.code, "source_adapter_failed")

    def test_exact_and_keyword_retrieval_include_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            retriever = _fixture_retriever(temp)

            exact = retriever.retrieve("second brain storage persistence sqlite")
            keyword = retriever.retrieve("MQTT broker status")

        self.assertEqual(exact.status, SourceRetrievalStatus.FOUND)
        self.assertEqual(keyword.status, SourceRetrievalStatus.FOUND)
        self.assertIn("local_markdown", exact.provenance[0])
        self.assertIn("mqtt_status_current", keyword.selected_document.source_id)

    def test_source_authority_and_freshness_ranking(self):
        current = _record(
            "authority_current",
            "Project state says source authority current truth wins.",
            authority=SourceAuthority.PROJECT_STATE,
            contradicted_by=("authority_note",),
        )
        note = _record(
            "authority_note",
            "A note says source authority note wins.",
            authority=SourceAuthority.NOTE,
            contradicted_by=("authority_current",),
        )
        result = _retriever_for_records((note, current)).retrieve("source authority wins")

        self.assertEqual(result.status, SourceRetrievalStatus.FOUND)
        self.assertEqual(result.selected_document.source_id, "authority_current")
        self.assertEqual(len(result.conflicting_documents), 1)

    def test_equal_authority_contradiction_does_not_invent_truth(self):
        with tempfile.TemporaryDirectory() as temp:
            retriever = _fixture_retriever(temp)

            result = retriever.retrieve("ambiguous source fixture")

        self.assertEqual(result.status, SourceRetrievalStatus.CONTRADICTED)
        self.assertIsNone(result.answer)
        self.assertEqual(len(result.conflicting_documents), 2)

    def test_unknown_query_does_not_fabricate_answer(self):
        with tempfile.TemporaryDirectory() as temp:
            retriever = _fixture_retriever(temp)

            result = retriever.retrieve("nonexistent orbital fixture")

        self.assertEqual(result.status, SourceRetrievalStatus.UNKNOWN)
        self.assertIsNone(result.answer)

    def test_deterministic_ordering_and_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            retriever = _fixture_retriever(temp)
            results = (retriever.retrieve("Pixel Watch validation"), retriever.retrieve("MQTT broker status"))
            renderer = SourceReportRenderer()

            text_a = renderer.render_text(results)
            text_b = renderer.render_text(results)
            json_a = renderer.render_json(results)
            json_b = renderer.render_json(results)

        self.assertEqual(text_a, text_b)
        self.assertEqual(json_a, json_b)
        self.assertEqual(json.loads(json_a)["mode"], "local_source_index")

    def test_user_scope_isolation(self):
        system = _record("system_doc", "Scoped fixture belongs to system.", user_scope="system")
        primary = _record("primary_doc", "Scoped fixture belongs to primary user.", user_scope="primary_user")
        result = _retriever_for_records((system, primary)).retrieve("scoped fixture", user_scope="primary_user")

        self.assertEqual(result.status, SourceRetrievalStatus.FOUND)
        self.assertEqual(result.selected_document.user_scope, "primary_user")

    def test_malformed_index_schema_fails_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "source-index.sqlite"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE source_index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute(
                    "INSERT INTO source_index_metadata (key, value) VALUES ('schema_version', '1')"
                )
                connection.execute("CREATE TABLE indexed_source_documents (document_id TEXT PRIMARY KEY)")
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(SourceIndexError) as raised:
                SQLiteSourceIndex(db_path).list()

        self.assertEqual(raised.exception.code, "source_index_corrupt")

    def test_unsupported_index_schema_fails_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "source-index.sqlite"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("CREATE TABLE source_index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute(
                    "INSERT INTO source_index_metadata (key, value) VALUES ('schema_version', '999')"
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(SourceIndexError) as raised:
                SQLiteSourceIndex(db_path).initialize()

        self.assertEqual(raised.exception.code, "source_index_schema_version_unsupported")

    def test_no_runtime_provider_network_imports(self):
        import jarvis_core.second_brain.index as source_index
        import jarvis_core.second_brain.source_retrieval as source_retrieval
        import jarvis_core.second_brain.sources as sources

        module_names = " ".join(
            (
                str(source_index.__dict__.keys()),
                str(source_retrieval.__dict__.keys()),
                str(sources.__dict__.keys()),
            )
        )
        for forbidden in ("Runtime", "Planner", "Driver", "DeviceState", "requests", "urllib", "socket"):
            self.assertNotIn(forbidden, module_names)

    def test_source_index_cli_is_explicit_and_local(self):
        with tempfile.TemporaryDirectory() as temp:
            source_dir, db_path = _source_and_db(temp)
            command = (
                sys.executable,
                "-m",
                "jarvis_core.second_brain",
                "--retrieval",
                "source",
                "--source-index",
                str(db_path),
                "--source-dir",
                str(source_dir),
                "--index-fixtures",
                "--query",
                "Second Brain durable storage",
                "--format",
                "json",
            )

            result = subprocess.run(command, check=False, capture_output=True, text=True, cwd=Path(__file__).parents[1])

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["mode"], "local_source_index")
        self.assertEqual(payload["results"][0]["status"], "found")

    def test_github_adapter_maps_project_state_authority_and_provenance(self):
        transport = FakeGitHubTransport(
            {
                "docs/project/PROJECT_STATE.md": "# JarvisOS Project State\n\nSecond Brain Phase 3/4 Foundation Slice.",
            }
        )
        adapter = GitHubSourceAdapter(
            repository="owner/repo",
            ref="main",
            paths=("docs/project/PROJECT_STATE.md",),
            transport=transport,
        )

        records = adapter.enumerate_records()

        self.assertEqual(adapter.source_scope, "github:owner/repo:main")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_type, SourceType.GITHUB)
        self.assertEqual(records[0].authority, SourceAuthority.PROJECT_STATE)
        self.assertIn("github.com/owner/repo/blob/commit-main/docs/project/PROJECT_STATE.md", records[0].source_reference)
        self.assertEqual(records[0].sensitivity, KnowledgeSensitivity.ORDINARY)

    def test_github_adapter_maps_accepted_adr_authority(self):
        transport = FakeGitHubTransport(
            {
                "docs/design/SECOND_BRAIN_MEMORY_BOUNDARY.md": (
                    "# ADR - Second Brain / Memory Boundary\n\nStatus: Accepted / Design - Not Implemented"
                ),
            }
        )
        adapter = GitHubSourceAdapter(
            repository="owner/repo",
            ref="main",
            paths=("docs/design/SECOND_BRAIN_MEMORY_BOUNDARY.md",),
            transport=transport,
        )

        record = adapter.enumerate_records()[0]

        self.assertEqual(record.authority, SourceAuthority.DESIGN_ADR)

    def test_github_source_index_persists_reopens_and_retrieves(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "source-index.sqlite"
            adapter = GitHubSourceAdapter(
                repository="owner/repo",
                ref="main",
                paths=("docs/project/PROJECT_STATE.md",),
                transport=FakeGitHubTransport(
                    {"docs/project/PROJECT_STATE.md": "# JarvisOS Project State\n\nGemini real provider validated."}
                ),
            )
            index = _initialized_index(db_path)
            summary = index.refresh(adapter)
            result = SourceHybridRetriever(index.list()).retrieve("Gemini provider validated")
            reopened = SourceHybridRetriever(_initialized_index(db_path).list()).retrieve(
                "Gemini provider validated"
            )

        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(result.status, SourceRetrievalStatus.FOUND)
        self.assertEqual(reopened.status, SourceRetrievalStatus.FOUND)
        self.assertEqual(result.selected_document, reopened.selected_document)

    def test_github_source_refresh_supersedes_prior_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "source-index.sqlite"
            index = _initialized_index(db_path)
            first = FakeGitHubTransport(
                {"docs/project/PROJECT_STATE.md": "# JarvisOS Project State\n\nOld current snapshot."},
                commit_sha="commit-old",
            )
            second = FakeGitHubTransport(
                {"docs/project/PROJECT_STATE.md": "# JarvisOS Project State\n\nNew current snapshot."},
                commit_sha="commit-new",
            )
            index.refresh(
                GitHubSourceAdapter(
                    repository="owner/repo",
                    ref="main",
                    paths=("docs/project/PROJECT_STATE.md",),
                    transport=first,
                )
            )

            summary = index.refresh(
                GitHubSourceAdapter(
                    repository="owner/repo",
                    ref="main",
                    paths=("docs/project/PROJECT_STATE.md",),
                    transport=second,
                )
            )
            all_docs = index.list(include_deleted=True)

        self.assertEqual(summary["inserted"], 1)
        self.assertEqual(summary["superseded"], 1)
        self.assertEqual(len([item for item in all_docs if item.freshness is KnowledgeFreshness.CURRENT]), 1)
        self.assertEqual(len([item for item in all_docs if item.freshness is KnowledgeFreshness.SUPERSEDED]), 1)

    def test_github_adapter_failure_is_bounded_by_source_index(self):
        with tempfile.TemporaryDirectory() as temp:
            index = _initialized_index(Path(temp) / "source-index.sqlite")
            adapter = GitHubSourceAdapter(
                repository="owner/repo",
                ref="main",
                paths=("docs/project/PROJECT_STATE.md",),
                transport=FailingGitHubTransport("github_source_unauthorized"),
            )

            with self.assertRaises(SourceIndexError) as raised:
                index.refresh(adapter)

        self.assertEqual(raised.exception.code, "source_adapter_failed")

    def test_github_adapter_rejects_unbounded_paths(self):
        with self.assertRaises(GitHubSourceError) as raised:
            GitHubSourceAdapter(
                repository="owner/repo",
                ref="main",
                paths=("../secret.md",),
                transport=FakeGitHubTransport({}),
            )

        self.assertEqual(raised.exception.code, "github_path_invalid")

    def test_github_source_cli_rejects_missing_repo(self):
        with tempfile.TemporaryDirectory() as temp:
            command = (
                sys.executable,
                "-m",
                "jarvis_core.second_brain",
                "--retrieval",
                "source",
                "--source-provider",
                "github",
                "--source-index",
                str(Path(temp) / "source-index.sqlite"),
            )

            result = subprocess.run(command, check=False, capture_output=True, text=True, cwd=Path(__file__).parents[1])

        self.assertEqual(result.returncode, 1)
        self.assertIn("github_repo_required", result.stderr)


def _source_and_db(temp: str) -> tuple[Path, Path]:
    base = Path(temp)
    return base / "sources", base / "source-index.sqlite"


def _initialized_index(db_path: Path) -> SQLiteSourceIndex:
    index = SQLiteSourceIndex(db_path)
    index.initialize()
    return index


def _fixture_retriever(temp: str) -> SourceHybridRetriever:
    source_dir, db_path = _source_and_db(temp)
    write_source_fixture_markdown(source_dir)
    index = _initialized_index(db_path)
    index.refresh(LocalMarkdownSourceAdapter(source_dir))
    return SourceHybridRetriever(index.list())


def _retriever_for_records(records: tuple[SourceRecord, ...]) -> SourceHybridRetriever:
    with tempfile.TemporaryDirectory() as temp:
        source_dir, db_path = _source_and_db(temp)
        for record in records:
            _write_record(source_dir, record)
        index = _initialized_index(db_path)
        index.refresh(LocalMarkdownSourceAdapter(source_dir))
        documents = index.list()
    return SourceHybridRetriever(documents)


def _record(
    source_id: str,
    content: str,
    *,
    authority: SourceAuthority = SourceAuthority.NOTE,
    user_scope: str = "system",
    contradicted_by: tuple[str, ...] = (),
) -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        source_type=SourceType.LOCAL_MARKDOWN,
        source_reference=f"fixtures/{source_id}.md",
        title=source_id.replace("_", " ").title(),
        topic=content,
        content=content,
        captured_at="2026-08-24T00:00:00Z",
        freshness=KnowledgeFreshness.CURRENT,
        authority=authority,
        confidence=KnowledgeConfidence.HIGH if authority is not SourceAuthority.NOTE else KnowledgeConfidence.MEDIUM,
        sensitivity=KnowledgeSensitivity.ORDINARY,
        user_scope=user_scope,
        contradicted_by=contradicted_by,
        safe_explanation="Synthetic source test fixture.",
    )


def _write_record(source_dir: Path, record: SourceRecord) -> Path:
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / f"{record.source_id}.md"
    path.write_text(render_markdown_source(record), encoding="utf-8")
    return path


def _document_for_source(index: SQLiteSourceIndex, source_id: str):
    matches = [
        document
        for document in index.list()
        if document.source_id == source_id and document.freshness is not KnowledgeFreshness.SUPERSEDED
    ]
    if not matches:
        raise AssertionError(f"Missing active source {source_id}")
    return matches[0]


class FakeGitHubTransport:
    def __init__(self, files: dict[str, str], *, commit_sha: str = "commit-main"):
        self._files = files
        self._commit_sha = commit_sha

    def fetch_file(self, repository: str, path: str, ref: str) -> GitHubFileSnapshot:
        if path not in self._files:
            raise GitHubSourceError("github_source_missing")
        return GitHubFileSnapshot(
            repository=repository,
            path=path,
            ref=ref,
            commit_sha=self._commit_sha,
            blob_sha=f"blob-{path}",
            html_url=f"https://github.com/{repository}/blob/{self._commit_sha}/{path}",
            content=self._files[path],
            fetched_at="2026-08-25T00:00:00Z",
        )


class FailingGitHubTransport:
    def __init__(self, code: str):
        self._code = code

    def fetch_file(self, repository: str, path: str, ref: str) -> GitHubFileSnapshot:
        raise GitHubSourceError(self._code)


if __name__ == "__main__":
    unittest.main()
