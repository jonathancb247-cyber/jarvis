"""Deterministic local source index for Second Brain source fixtures."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterator, Sequence

from .models import KnowledgeConfidence, KnowledgeFreshness, KnowledgeSensitivity
from .sources import (
    IndexedSourceDocument,
    SourceAdapter,
    SourceAuthority,
    SourceRecord,
    SourceType,
)


SOURCE_INDEX_SCHEMA_VERSION = 1


class SourceIndexError(Exception):
    """Safe source-index failure with a bounded code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SQLiteSourceIndex:
    """Local SQLite source index for deterministic fixture validation.

    This index is separate from the Phase 2 durable KnowledgeItem repository.
    It stores indexed source snapshots, not personal memory and not Runtime
    state.
    """

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS source_index_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                current = connection.execute(
                    "SELECT value FROM source_index_metadata WHERE key = ?",
                    ("schema_version",),
                ).fetchone()
                if current is None:
                    connection.execute(
                        "INSERT INTO source_index_metadata (key, value) VALUES (?, ?)",
                        ("schema_version", str(SOURCE_INDEX_SCHEMA_VERSION)),
                    )
                elif current[0] != str(SOURCE_INDEX_SCHEMA_VERSION):
                    raise SourceIndexError("source_index_schema_version_unsupported")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS indexed_source_documents (
                        document_id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        source_reference TEXT NOT NULL,
                        title TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        content TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        freshness TEXT NOT NULL,
                        authority TEXT NOT NULL,
                        confidence TEXT NOT NULL,
                        sensitivity TEXT NOT NULL,
                        user_scope TEXT NOT NULL,
                        supersedes_json TEXT NOT NULL,
                        superseded_by_json TEXT NOT NULL,
                        contradicted_by_json TEXT NOT NULL,
                        deleted INTEGER NOT NULL DEFAULT 0,
                        safe_explanation TEXT NOT NULL
                    )
                    """
                )
                _assert_schema(connection)
        except SourceIndexError:
            raise
        except sqlite3.DatabaseError as exc:
            raise SourceIndexError("source_index_corrupt") from exc
        except OSError as exc:
            raise SourceIndexError("source_index_unavailable") from exc

    def refresh(self, adapter: SourceAdapter) -> dict[str, int]:
        records = adapter.enumerate_records()
        seen_source_ids = {record.source_id for record in records}
        inserted = 0
        unchanged = 0
        superseded = 0
        deleted = 0
        try:
            with self._connection_checked() as connection:
                for record in records:
                    _validate_record(record)
                    document = _document_from_record(record)
                    existing_same_hash = connection.execute(
                        """
                        SELECT rowid, * FROM indexed_source_documents
                        WHERE source_id = ? AND content_hash = ? AND deleted = 0
                        """,
                        (record.source_id, document.content_hash),
                    ).fetchone()
                    if existing_same_hash is not None:
                        unchanged += 1
                        continue

                    active_rows = connection.execute(
                        """
                        SELECT rowid, * FROM indexed_source_documents
                        WHERE source_id = ? AND deleted = 0
                        """,
                        (record.source_id,),
                    ).fetchall()
                    supersedes = tuple(_document_from_row(row).document_id for row in active_rows)
                    document = IndexedSourceDocument(
                        **{**document.__dict__, "supersedes": supersedes}
                    )
                    connection.execute(_INSERT_SQL, _document_values(document))
                    inserted += 1
                    for old_id in supersedes:
                        connection.execute(
                            """
                            UPDATE indexed_source_documents
                            SET freshness = ?, superseded_by_json = ?
                            WHERE document_id = ?
                            """,
                            (
                                KnowledgeFreshness.SUPERSEDED.value,
                                _encode_ids((document.document_id,)),
                                old_id,
                            ),
                        )
                        superseded += 1

                active_rows = connection.execute(
                    "SELECT rowid, * FROM indexed_source_documents WHERE deleted = 0"
                ).fetchall()
                for row in active_rows:
                    document = _document_from_row(row)
                    if document.source_id not in seen_source_ids:
                        connection.execute(
                            """
                            UPDATE indexed_source_documents
                            SET deleted = 1, freshness = ?
                            WHERE document_id = ?
                            """,
                            (KnowledgeFreshness.STALE.value, document.document_id),
                        )
                        deleted += 1
        except SourceIndexError:
            raise
        except sqlite3.IntegrityError as exc:
            raise SourceIndexError("source_index_duplicate") from exc
        except sqlite3.DatabaseError as exc:
            raise SourceIndexError("source_index_write_failed") from exc
        return {
            "inserted": inserted,
            "unchanged": unchanged,
            "superseded": superseded,
            "deleted": deleted,
        }

    def list(
        self,
        *,
        user_scope: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[IndexedSourceDocument, ...]:
        sql = "SELECT rowid, * FROM indexed_source_documents"
        clauses = []
        values: list[object] = []
        if not include_deleted:
            clauses.append("deleted = 0")
        if user_scope is not None:
            clauses.append("user_scope = ?")
            values.append(user_scope)
        if clauses:
            sql = f"{sql} WHERE {' AND '.join(clauses)}"
        sql = f"{sql} ORDER BY rowid ASC"
        try:
            with self._connection_checked() as connection:
                rows = connection.execute(sql, tuple(values)).fetchall()
        except sqlite3.DatabaseError as exc:
            raise SourceIndexError("source_index_corrupt") from exc
        return tuple(_document_from_row(row) for row in rows)

    def get(self, document_id: str, *, include_deleted: bool = False) -> IndexedSourceDocument | None:
        sql = "SELECT rowid, * FROM indexed_source_documents WHERE document_id = ?"
        if not include_deleted:
            sql = f"{sql} AND deleted = 0"
        try:
            with self._connection_checked() as connection:
                row = connection.execute(sql, (document_id,)).fetchone()
        except sqlite3.DatabaseError as exc:
            raise SourceIndexError("source_index_corrupt") from exc
        return _document_from_row(row) if row is not None else None

    @contextmanager
    def _connection_checked(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            _check_schema_version(connection)
            _assert_schema(connection)
            yield connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self._db_path)
        except sqlite3.DatabaseError as exc:
            raise SourceIndexError("source_index_corrupt") from exc
        except OSError as exc:
            raise SourceIndexError("source_index_unavailable") from exc
        connection.row_factory = sqlite3.Row
        return connection


_INSERT_SQL = """
INSERT INTO indexed_source_documents (
    document_id, source_id, source_type, source_reference, title, topic,
    content, content_hash, captured_at, freshness, authority, confidence,
    sensitivity, user_scope, supersedes_json, superseded_by_json,
    contradicted_by_json, deleted, safe_explanation
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _document_from_record(record: SourceRecord) -> IndexedSourceDocument:
    content_hash = _content_hash(record)
    return IndexedSourceDocument(
        document_id=f"{record.source_id}@{content_hash[:12]}",
        source_id=record.source_id,
        source_type=record.source_type,
        source_reference=record.source_reference,
        title=record.title,
        topic=record.topic,
        content=record.content,
        content_hash=content_hash,
        captured_at=record.captured_at,
        freshness=record.freshness,
        authority=record.authority,
        confidence=record.confidence,
        sensitivity=record.sensitivity,
        user_scope=record.user_scope,
        contradicted_by=record.contradicted_by,
        safe_explanation=record.safe_explanation,
    )


def _content_hash(record: SourceRecord) -> str:
    payload = "\n".join(
        (
            record.source_id,
            record.source_type.value,
            record.source_reference,
            record.title,
            record.topic,
            record.content,
            record.captured_at,
            record.freshness.value,
            record.authority.value,
            record.confidence.value,
            record.sensitivity.value,
            record.user_scope,
            ",".join(record.contradicted_by),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _document_values(document: IndexedSourceDocument) -> tuple[object, ...]:
    return (
        document.document_id,
        document.source_id,
        document.source_type.value,
        document.source_reference,
        document.title,
        document.topic,
        document.content,
        document.content_hash,
        document.captured_at,
        document.freshness.value,
        document.authority.value,
        document.confidence.value,
        document.sensitivity.value,
        document.user_scope,
        _encode_ids(document.supersedes),
        _encode_ids(document.superseded_by),
        _encode_ids(document.contradicted_by),
        int(document.deleted),
        document.safe_explanation,
    )


def _document_from_row(row: sqlite3.Row) -> IndexedSourceDocument:
    try:
        return IndexedSourceDocument(
            document_id=_required_text(row["document_id"]),
            source_id=_required_text(row["source_id"]),
            source_type=SourceType(row["source_type"]),
            source_reference=_required_text(row["source_reference"]),
            title=_required_text(row["title"]),
            topic=_required_text(row["topic"]),
            content=_required_text(row["content"]),
            content_hash=_required_text(row["content_hash"]),
            captured_at=_required_text(row["captured_at"]),
            freshness=KnowledgeFreshness(row["freshness"]),
            authority=SourceAuthority(row["authority"]),
            confidence=KnowledgeConfidence(row["confidence"]),
            sensitivity=KnowledgeSensitivity(row["sensitivity"]),
            user_scope=_required_text(row["user_scope"]),
            supersedes=_decode_ids(row["supersedes_json"]),
            superseded_by=_decode_ids(row["superseded_by_json"]),
            contradicted_by=_decode_ids(row["contradicted_by_json"]),
            deleted=bool(row["deleted"]),
            safe_explanation=_required_text(row["safe_explanation"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SourceIndexError("source_index_corrupt") from exc


def _assert_schema(connection: sqlite3.Connection) -> None:
    columns = tuple(row[1] for row in connection.execute("PRAGMA table_info(indexed_source_documents)").fetchall())
    required = (
        "document_id",
        "source_id",
        "source_type",
        "source_reference",
        "title",
        "topic",
        "content",
        "content_hash",
        "captured_at",
        "freshness",
        "authority",
        "confidence",
        "sensitivity",
        "user_scope",
        "supersedes_json",
        "superseded_by_json",
        "contradicted_by_json",
        "deleted",
        "safe_explanation",
    )
    if tuple(column for column in columns if column in required) != required:
        raise SourceIndexError("source_index_corrupt")


def _check_schema_version(connection: sqlite3.Connection) -> None:
    try:
        value = connection.execute(
            "SELECT value FROM source_index_metadata WHERE key = ?",
            ("schema_version",),
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise SourceIndexError("source_index_corrupt") from exc
    if value is None:
        raise SourceIndexError("source_index_corrupt")
    if value[0] != str(SOURCE_INDEX_SCHEMA_VERSION):
        raise SourceIndexError("source_index_schema_version_unsupported")


def _validate_record(record: SourceRecord) -> None:
    if not isinstance(record, SourceRecord):
        raise SourceIndexError("source_record_invalid")
    if record.sensitivity is not KnowledgeSensitivity.ORDINARY:
        raise SourceIndexError("source_record_unsupported_sensitivity")
    text_fields = (
        record.source_id,
        record.source_reference,
        record.title,
        record.topic,
        record.content,
        record.captured_at,
        record.user_scope,
    )
    if any(not isinstance(value, str) or not value.strip() for value in text_fields):
        raise SourceIndexError("source_record_invalid")
    if not all(isinstance(item, str) and item for item in record.contradicted_by):
        raise SourceIndexError("source_record_invalid")


def _encode_ids(values: Sequence[str]) -> str:
    if not all(isinstance(item, str) and item for item in values):
        raise SourceIndexError("source_record_invalid")
    return json.dumps(list(values), separators=(",", ":"))


def _decode_ids(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not all(isinstance(item, str) and item for item in decoded):
        raise SourceIndexError("source_index_corrupt")
    return tuple(decoded)


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise SourceIndexError("source_index_corrupt")
    return value

