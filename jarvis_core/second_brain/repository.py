"""Fixture-only Second Brain repositories.

The SQLite repository is a local diagnostic storage adapter for synthetic
fixtures only. It does not make SQLite a core JarvisOS dependency and it never
authorizes execution, connectors, providers, or real personal memory.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from typing import Iterator, Iterable, Sequence

from .models import (
    KnowledgeConfidence,
    KnowledgeFreshness,
    KnowledgeItem,
    KnowledgeKind,
    KnowledgeOrigin,
    KnowledgeSensitivity,
)


SECOND_BRAIN_SCHEMA_VERSION = 1

ALLOWED_USER_SCOPES = frozenset(("system", "primary_user", "household", "guest_session", "unknown"))
_BLOCKED_FIXTURE_TERMS = (
    "credential",
    "password",
    "token",
    "secret",
    "heart rate",
    "hrv",
    "sleep",
    "bank",
    "financial",
    "private message",
    "precise location",
    "biometric",
    "intimate",
    "relationship",
)


class SecondBrainStorageError(Exception):
    """Safe storage failure with a bounded machine-readable code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class KnowledgeRepository:
    """Narrow fixture knowledge repository boundary."""

    def insert(self, item: KnowledgeItem) -> KnowledgeItem:
        raise NotImplementedError

    def get(self, knowledge_id: str, *, include_deleted: bool = False) -> KnowledgeItem | None:
        raise NotImplementedError

    def list(
        self,
        *,
        user_scope: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[KnowledgeItem, ...]:
        raise NotImplementedError

    def correct(self, prior_knowledge_id: str, correction: KnowledgeItem) -> KnowledgeItem:
        raise NotImplementedError

    def logical_delete(self, knowledge_id: str) -> bool:
        raise NotImplementedError

    def hard_purge(self, knowledge_id: str) -> bool:
        raise NotImplementedError


class InMemoryKnowledgeRepository(KnowledgeRepository):
    """Deterministic in-memory repository used by tests and diagnostics."""

    def __init__(self, items: Sequence[KnowledgeItem] | None = None):
        self._items: list[KnowledgeItem] = []
        self._deleted: set[str] = set()
        for item in items or ():
            self.insert(item)

    def insert(self, item: KnowledgeItem) -> KnowledgeItem:
        _validate_fixture_item(item)
        if any(existing.knowledge_id == item.knowledge_id for existing in self._items):
            raise SecondBrainStorageError("duplicate_knowledge_id")
        self._items.append(item)
        return item

    def get(self, knowledge_id: str, *, include_deleted: bool = False) -> KnowledgeItem | None:
        for item in self._items:
            if item.knowledge_id == knowledge_id and (include_deleted or knowledge_id not in self._deleted):
                return item
        return None

    def list(
        self,
        *,
        user_scope: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[KnowledgeItem, ...]:
        _validate_scope(user_scope)
        return tuple(
            item
            for item in self._items
            if (include_deleted or item.knowledge_id not in self._deleted)
            and (user_scope is None or item.user_scope == user_scope)
        )

    def correct(self, prior_knowledge_id: str, correction: KnowledgeItem) -> KnowledgeItem:
        prior = self.get(prior_knowledge_id)
        if prior is None:
            raise SecondBrainStorageError("knowledge_not_found")
        correction = _ensure_supersedes(correction, prior_knowledge_id)
        updated_prior = replace(
            prior,
            freshness=KnowledgeFreshness.SUPERSEDED,
            superseded_by=_append_unique(prior.superseded_by, correction.knowledge_id),
        )
        index = self._items.index(prior)
        self.insert(correction)
        self._items[index] = updated_prior
        return correction

    def logical_delete(self, knowledge_id: str) -> bool:
        if self.get(knowledge_id, include_deleted=True) is None:
            return False
        self._deleted.add(knowledge_id)
        return True

    def hard_purge(self, knowledge_id: str) -> bool:
        before = len(self._items)
        self._items = [item for item in self._items if item.knowledge_id != knowledge_id]
        self._deleted.discard(knowledge_id)
        return len(self._items) != before


class SQLiteKnowledgeRepository(KnowledgeRepository):
    """Local SQLite storage adapter for synthetic fixture validation."""

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
                    CREATE TABLE IF NOT EXISTS second_brain_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                current = connection.execute(
                    "SELECT value FROM second_brain_metadata WHERE key = ?",
                    ("schema_version",),
                ).fetchone()
                if current is None:
                    connection.execute(
                        "INSERT INTO second_brain_metadata (key, value) VALUES (?, ?)",
                        ("schema_version", str(SECOND_BRAIN_SCHEMA_VERSION)),
                    )
                elif current[0] != str(SECOND_BRAIN_SCHEMA_VERSION):
                    raise SecondBrainStorageError("schema_version_unsupported")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS knowledge_items (
                        knowledge_id TEXT PRIMARY KEY,
                        kind TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        source_reference TEXT NOT NULL,
                        freshness TEXT NOT NULL,
                        confidence TEXT NOT NULL,
                        origin TEXT NOT NULL,
                        sensitivity TEXT NOT NULL,
                        user_scope TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        supersedes_json TEXT NOT NULL,
                        superseded_by_json TEXT NOT NULL,
                        contradicted_by_json TEXT NOT NULL,
                        safe_explanation TEXT NOT NULL,
                        deleted INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
                _assert_schema(connection)
        except SecondBrainStorageError:
            raise
        except sqlite3.DatabaseError as exc:
            raise SecondBrainStorageError("storage_corrupt") from exc
        except OSError as exc:
            raise SecondBrainStorageError("storage_unavailable") from exc

    def schema_version(self) -> int:
        try:
            with self._connection() as connection:
                value = connection.execute(
                    "SELECT value FROM second_brain_metadata WHERE key = ?",
                    ("schema_version",),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise SecondBrainStorageError("storage_corrupt") from exc
        if value is None:
            raise SecondBrainStorageError("storage_corrupt")
        if value[0] != str(SECOND_BRAIN_SCHEMA_VERSION):
            raise SecondBrainStorageError("schema_version_unsupported")
        return SECOND_BRAIN_SCHEMA_VERSION

    def health(self) -> dict[str, int]:
        try:
            with self._connection_checked() as connection:
                count = connection.execute("SELECT COUNT(*) FROM knowledge_items WHERE deleted = 0").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise SecondBrainStorageError("storage_corrupt") from exc
        return {"schema_version": SECOND_BRAIN_SCHEMA_VERSION, "item_count": int(count)}

    def insert(self, item: KnowledgeItem) -> KnowledgeItem:
        _validate_fixture_item(item)
        try:
            with self._connection_checked() as connection:
                connection.execute(
                    """
                    INSERT INTO knowledge_items (
                        knowledge_id, kind, topic, summary, source_type, source_reference,
                        freshness, confidence, origin, sensitivity, user_scope, captured_at,
                        supersedes_json, superseded_by_json, contradicted_by_json,
                        safe_explanation, deleted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    _item_values(item),
                )
        except sqlite3.IntegrityError as exc:
            raise SecondBrainStorageError("duplicate_knowledge_id") from exc
        except sqlite3.DatabaseError as exc:
            raise SecondBrainStorageError("write_failed") from exc
        return item

    def get(self, knowledge_id: str, *, include_deleted: bool = False) -> KnowledgeItem | None:
        sql = "SELECT rowid, * FROM knowledge_items WHERE knowledge_id = ?"
        values: tuple[object, ...] = (knowledge_id,)
        if not include_deleted:
            sql = f"{sql} AND deleted = 0"
        try:
            with self._connection_checked() as connection:
                row = connection.execute(sql, values).fetchone()
        except sqlite3.DatabaseError as exc:
            raise SecondBrainStorageError("storage_corrupt") from exc
        return _item_from_row(row) if row is not None else None

    def list(
        self,
        *,
        user_scope: str | None = None,
        include_deleted: bool = False,
    ) -> tuple[KnowledgeItem, ...]:
        _validate_scope(user_scope)
        sql = "SELECT rowid, * FROM knowledge_items"
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
            raise SecondBrainStorageError("storage_corrupt") from exc
        return tuple(_item_from_row(row) for row in rows)

    def correct(self, prior_knowledge_id: str, correction: KnowledgeItem) -> KnowledgeItem:
        correction = _ensure_supersedes(correction, prior_knowledge_id)
        _validate_fixture_item(correction)
        try:
            with self._connection_checked() as connection:
                prior_row = connection.execute(
                    "SELECT rowid, * FROM knowledge_items WHERE knowledge_id = ? AND deleted = 0",
                    (prior_knowledge_id,),
                ).fetchone()
                if prior_row is None:
                    raise SecondBrainStorageError("knowledge_not_found")
                prior = _item_from_row(prior_row)
                updated_prior = replace(
                    prior,
                    freshness=KnowledgeFreshness.SUPERSEDED,
                    superseded_by=_append_unique(prior.superseded_by, correction.knowledge_id),
                )
                connection.execute(
                    """
                    INSERT INTO knowledge_items (
                        knowledge_id, kind, topic, summary, source_type, source_reference,
                        freshness, confidence, origin, sensitivity, user_scope, captured_at,
                        supersedes_json, superseded_by_json, contradicted_by_json,
                        safe_explanation, deleted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    _item_values(correction),
                )
                connection.execute(
                    """
                    UPDATE knowledge_items
                    SET freshness = ?, superseded_by_json = ?
                    WHERE knowledge_id = ?
                    """,
                    (
                        updated_prior.freshness.value,
                        _encode_ids(updated_prior.superseded_by),
                        prior_knowledge_id,
                    ),
                )
        except SecondBrainStorageError:
            raise
        except sqlite3.IntegrityError as exc:
            raise SecondBrainStorageError("duplicate_knowledge_id") from exc
        except sqlite3.DatabaseError as exc:
            raise SecondBrainStorageError("write_failed") from exc
        return correction

    def logical_delete(self, knowledge_id: str) -> bool:
        try:
            with self._connection_checked() as connection:
                cursor = connection.execute(
                    "UPDATE knowledge_items SET deleted = 1 WHERE knowledge_id = ?",
                    (knowledge_id,),
                )
        except sqlite3.DatabaseError as exc:
            raise SecondBrainStorageError("storage_corrupt") from exc
        return cursor.rowcount > 0

    def hard_purge(self, knowledge_id: str) -> bool:
        try:
            with self._connection_checked() as connection:
                cursor = connection.execute("DELETE FROM knowledge_items WHERE knowledge_id = ?", (knowledge_id,))
        except sqlite3.DatabaseError as exc:
            raise SecondBrainStorageError("storage_corrupt") from exc
        return cursor.rowcount > 0

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
            raise SecondBrainStorageError("storage_corrupt") from exc
        except OSError as exc:
            raise SecondBrainStorageError("storage_unavailable") from exc
        connection.row_factory = sqlite3.Row
        return connection


def seed_repository(repository: KnowledgeRepository, items: Iterable[KnowledgeItem]) -> int:
    count = 0
    for item in items:
        repository.insert(item)
        count += 1
    return count


def _assert_schema(connection: sqlite3.Connection) -> None:
    columns = tuple(row[1] for row in connection.execute("PRAGMA table_info(knowledge_items)").fetchall())
    required = (
        "knowledge_id",
        "kind",
        "topic",
        "summary",
        "source_type",
        "source_reference",
        "freshness",
        "confidence",
        "origin",
        "sensitivity",
        "user_scope",
        "captured_at",
        "supersedes_json",
        "superseded_by_json",
        "contradicted_by_json",
        "safe_explanation",
        "deleted",
    )
    if tuple(column for column in columns if column in required) != required:
        raise SecondBrainStorageError("storage_corrupt")


def _check_schema_version(connection: sqlite3.Connection) -> None:
    try:
        value = connection.execute(
            "SELECT value FROM second_brain_metadata WHERE key = ?",
            ("schema_version",),
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        raise SecondBrainStorageError("storage_corrupt") from exc
    if value is None:
        raise SecondBrainStorageError("storage_corrupt")
    if value[0] != str(SECOND_BRAIN_SCHEMA_VERSION):
        raise SecondBrainStorageError("schema_version_unsupported")


def _item_values(item: KnowledgeItem) -> tuple[object, ...]:
    return (
        item.knowledge_id,
        item.kind.value,
        item.topic,
        item.summary,
        item.source_type,
        item.source_reference,
        item.freshness.value,
        item.confidence.value,
        item.origin.value,
        item.sensitivity.value,
        item.user_scope,
        item.captured_at,
        _encode_ids(item.supersedes),
        _encode_ids(item.superseded_by),
        _encode_ids(item.contradicted_by),
        item.safe_explanation,
    )


def _item_from_row(row: sqlite3.Row) -> KnowledgeItem:
    try:
        return KnowledgeItem(
            knowledge_id=_required_text(row["knowledge_id"]),
            kind=KnowledgeKind(row["kind"]),
            topic=_required_text(row["topic"]),
            summary=_required_text(row["summary"]),
            source_type=_required_text(row["source_type"]),
            source_reference=_required_text(row["source_reference"]),
            freshness=KnowledgeFreshness(row["freshness"]),
            confidence=KnowledgeConfidence(row["confidence"]),
            origin=KnowledgeOrigin(row["origin"]),
            sensitivity=KnowledgeSensitivity(row["sensitivity"]),
            user_scope=_required_text(row["user_scope"]),
            captured_at=_required_text(row["captured_at"]),
            supersedes=_decode_ids(row["supersedes_json"]),
            superseded_by=_decode_ids(row["superseded_by_json"]),
            contradicted_by=_decode_ids(row["contradicted_by_json"]),
            safe_explanation=_required_text(row["safe_explanation"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SecondBrainStorageError("storage_corrupt") from exc


def _validate_fixture_item(item: KnowledgeItem) -> None:
    if not isinstance(item, KnowledgeItem):
        raise SecondBrainStorageError("invalid_knowledge_item")
    enum_checks = (
        (item.kind, KnowledgeKind),
        (item.freshness, KnowledgeFreshness),
        (item.confidence, KnowledgeConfidence),
        (item.origin, KnowledgeOrigin),
        (item.sensitivity, KnowledgeSensitivity),
    )
    if any(not isinstance(value, enum_type) for value, enum_type in enum_checks):
        raise SecondBrainStorageError("invalid_knowledge_item")
    if item.sensitivity is not KnowledgeSensitivity.ORDINARY:
        raise SecondBrainStorageError("unsupported_sensitivity")
    _validate_scope(item.user_scope)
    text_fields = (
        item.knowledge_id,
        item.topic,
        item.summary,
        item.source_type,
        item.source_reference,
        item.captured_at,
        item.safe_explanation,
    )
    if any(not isinstance(value, str) or not value.strip() for value in text_fields[:6]):
        raise SecondBrainStorageError("invalid_knowledge_item")
    if not all(_is_id_tuple(value) for value in (item.supersedes, item.superseded_by, item.contradicted_by)):
        raise SecondBrainStorageError("invalid_knowledge_item")
    combined = " ".join((item.topic, item.summary, item.source_reference, item.safe_explanation)).lower()
    if any(term in combined for term in _BLOCKED_FIXTURE_TERMS):
        raise SecondBrainStorageError("unsupported_sensitivity")


def _validate_scope(user_scope: str | None) -> None:
    if user_scope is not None and user_scope not in ALLOWED_USER_SCOPES:
        raise SecondBrainStorageError("invalid_user_scope")


def _is_id_tuple(value: object) -> bool:
    return isinstance(value, tuple) and all(isinstance(item, str) and item for item in value)


def _ensure_supersedes(item: KnowledgeItem, prior_knowledge_id: str) -> KnowledgeItem:
    return replace(item, supersedes=_append_unique(item.supersedes, prior_knowledge_id))


def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    if value in values:
        return values
    return (*values, value)


def _encode_ids(values: tuple[str, ...]) -> str:
    if not _is_id_tuple(values):
        raise SecondBrainStorageError("invalid_knowledge_item")
    return json.dumps(list(values), separators=(",", ":"))


def _decode_ids(value: str) -> tuple[str, ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not all(isinstance(item, str) and item for item in decoded):
        raise SecondBrainStorageError("storage_corrupt")
    return tuple(decoded)


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise SecondBrainStorageError("storage_corrupt")
    return value
