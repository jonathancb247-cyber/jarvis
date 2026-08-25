"""Local source document fixtures for Second Brain source indexing.

This module is intentionally local and deterministic. It does not implement
live external connectors, network access, credentials, or automatic indexing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Iterable

from .models import KnowledgeConfidence, KnowledgeFreshness, KnowledgeSensitivity


SOURCE_FIXTURE_CAPTURED_AT = "2026-08-24T00:00:00Z"


class SourceType(str, Enum):
    LOCAL_MARKDOWN = "local_markdown"
    GITHUB = "github"
    NOTION = "notion"
    OBSIDIAN_MARKDOWN = "obsidian_markdown"
    GOOGLE_DRIVE = "google_drive"


class SourceAuthority(str, Enum):
    FIXTURE = "fixture"
    PROJECT_STATE = "project_state"
    DESIGN_ADR = "design_adr"
    HISTORICAL = "historical"
    NOTE = "note"


class SourceRetrievalStatus(str, Enum):
    FOUND = "found"
    UNKNOWN = "unknown"
    CONTRADICTED = "contradicted"


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_type: SourceType
    source_reference: str
    title: str
    topic: str
    content: str
    captured_at: str
    freshness: KnowledgeFreshness
    authority: SourceAuthority
    confidence: KnowledgeConfidence
    sensitivity: KnowledgeSensitivity
    user_scope: str
    contradicted_by: tuple[str, ...] = ()
    safe_explanation: str = ""


@dataclass(frozen=True)
class IndexedSourceDocument:
    document_id: str
    source_id: str
    source_type: SourceType
    source_reference: str
    title: str
    topic: str
    content: str
    content_hash: str
    captured_at: str
    freshness: KnowledgeFreshness
    authority: SourceAuthority
    confidence: KnowledgeConfidence
    sensitivity: KnowledgeSensitivity
    user_scope: str
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    contradicted_by: tuple[str, ...] = ()
    deleted: bool = False
    safe_explanation: str = ""


@dataclass(frozen=True)
class SourceRetrievalResult:
    query: str
    status: SourceRetrievalStatus
    answer: str | None
    selected_document: IndexedSourceDocument | None
    supporting_documents: tuple[IndexedSourceDocument, ...]
    conflicting_documents: tuple[IndexedSourceDocument, ...]
    superseded_documents: tuple[IndexedSourceDocument, ...]
    provenance: tuple[str, ...]
    freshness: KnowledgeFreshness | None
    confidence: KnowledgeConfidence | None
    relevance: int
    safe_explanation: str


class SourceAdapter:
    """Narrow future connector boundary.

    Future live adapters may enumerate source records, but this phase only
    implements local Markdown fixtures.
    """

    def enumerate_records(self) -> tuple[SourceRecord, ...]:
        raise NotImplementedError


class LocalMarkdownSourceAdapter(SourceAdapter):
    """Parse deterministic local Markdown fixture files."""

    def __init__(self, source_dir: str | Path):
        self._source_dir = Path(source_dir)

    def enumerate_records(self) -> tuple[SourceRecord, ...]:
        records = []
        for path in sorted(self._source_dir.glob("*.md"), key=lambda item: item.name):
            records.append(parse_markdown_source(path))
        return tuple(records)


def parse_markdown_source(path: str | Path) -> SourceRecord:
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8")
    metadata, content = _split_front_matter(text)
    return SourceRecord(
        source_id=_required(metadata, "source_id"),
        source_type=SourceType(_required(metadata, "source_type")),
        source_reference=_required(metadata, "source_reference"),
        title=_required(metadata, "title"),
        topic=_required(metadata, "topic"),
        content=content.strip(),
        captured_at=metadata.get("captured_at", SOURCE_FIXTURE_CAPTURED_AT),
        freshness=KnowledgeFreshness(_required(metadata, "freshness")),
        authority=SourceAuthority(_required(metadata, "authority")),
        confidence=KnowledgeConfidence(_required(metadata, "confidence")),
        sensitivity=KnowledgeSensitivity(_required(metadata, "sensitivity")),
        user_scope=_required(metadata, "user_scope"),
        contradicted_by=_split_ids(metadata.get("contradicted_by", "")),
        safe_explanation=metadata.get("safe_explanation", "Local deterministic source fixture."),
    )


def build_source_fixture_records() -> tuple[SourceRecord, ...]:
    """Return synthetic source records with no personal or sensitive data."""

    return (
        SourceRecord(
            source_id="wearable_status_old",
            source_type=SourceType.LOCAL_MARKDOWN,
            source_reference="fixtures/wearable-old.md",
            title="Wearable Status Old",
            topic="wearable pixel watch phase 1",
            content="Wearable Phase 1 was pending fake deterministic validation.",
            captured_at=SOURCE_FIXTURE_CAPTURED_AT,
            freshness=KnowledgeFreshness.SUPERSEDED,
            authority=SourceAuthority.HISTORICAL,
            confidence=KnowledgeConfidence.HIGH,
            sensitivity=KnowledgeSensitivity.ORDINARY,
            user_scope="system",
            safe_explanation="Historical local Markdown fixture retained only as superseded evidence.",
        ),
        SourceRecord(
            source_id="wearable_status_current",
            source_type=SourceType.LOCAL_MARKDOWN,
            source_reference="fixtures/wearable-current.md",
            title="Wearable Status Current",
            topic="wearable pixel watch phase 1",
            content="Wearable Phase 1 fake deterministic validation is complete; real Pixel Watch validation remains separate.",
            captured_at=SOURCE_FIXTURE_CAPTURED_AT,
            freshness=KnowledgeFreshness.CURRENT,
            authority=SourceAuthority.PROJECT_STATE,
            confidence=KnowledgeConfidence.HIGH,
            sensitivity=KnowledgeSensitivity.ORDINARY,
            user_scope="system",
            safe_explanation="Current project-state-like local Markdown fixture.",
        ),
        SourceRecord(
            source_id="mqtt_status_current",
            source_type=SourceType.LOCAL_MARKDOWN,
            source_reference="fixtures/mqtt-current.md",
            title="MQTT Status Current",
            topic="mqtt project status phase 12",
            content="MQTT request response is validated with local Mosquitto; physical ESP32 MQTT validation remains unresolved.",
            captured_at=SOURCE_FIXTURE_CAPTURED_AT,
            freshness=KnowledgeFreshness.CURRENT,
            authority=SourceAuthority.PROJECT_STATE,
            confidence=KnowledgeConfidence.HIGH,
            sensitivity=KnowledgeSensitivity.ORDINARY,
            user_scope="system",
            safe_explanation="Conservative source fixture avoids claiming ESP32 MQTT completion.",
        ),
        SourceRecord(
            source_id="second_brain_storage_adr",
            source_type=SourceType.LOCAL_MARKDOWN,
            source_reference="fixtures/second-brain-storage.md",
            title="Second Brain Storage ADR",
            topic="second brain storage persistence boundary sqlite",
            content="SQLite is approved as fixture-only storage adapter. It is not Runtime authority or real personal memory.",
            captured_at=SOURCE_FIXTURE_CAPTURED_AT,
            freshness=KnowledgeFreshness.CURRENT,
            authority=SourceAuthority.DESIGN_ADR,
            confidence=KnowledgeConfidence.HIGH,
            sensitivity=KnowledgeSensitivity.ORDINARY,
            user_scope="system",
            safe_explanation="Local ADR-like fixture describes storage boundary.",
        ),
        SourceRecord(
            source_id="ambiguous_source_enabled",
            source_type=SourceType.LOCAL_MARKDOWN,
            source_reference="fixtures/ambiguous-enabled.md",
            title="Ambiguous Source Enabled",
            topic="ambiguous source fixture",
            content="The ambiguous source fixture says the feature is enabled.",
            captured_at=SOURCE_FIXTURE_CAPTURED_AT,
            freshness=KnowledgeFreshness.CURRENT,
            authority=SourceAuthority.NOTE,
            confidence=KnowledgeConfidence.MEDIUM,
            sensitivity=KnowledgeSensitivity.ORDINARY,
            user_scope="system",
            contradicted_by=("ambiguous_source_paused",),
            safe_explanation="Equal-authority local fixture conflicts with another local fixture.",
        ),
        SourceRecord(
            source_id="ambiguous_source_paused",
            source_type=SourceType.LOCAL_MARKDOWN,
            source_reference="fixtures/ambiguous-paused.md",
            title="Ambiguous Source Paused",
            topic="ambiguous source fixture",
            content="The ambiguous source fixture says the feature is paused.",
            captured_at=SOURCE_FIXTURE_CAPTURED_AT,
            freshness=KnowledgeFreshness.CURRENT,
            authority=SourceAuthority.NOTE,
            confidence=KnowledgeConfidence.MEDIUM,
            sensitivity=KnowledgeSensitivity.ORDINARY,
            user_scope="system",
            contradicted_by=("ambiguous_source_enabled",),
            safe_explanation="Equal-authority local fixture conflicts with another local fixture.",
        ),
    )


def render_markdown_source(record: SourceRecord) -> str:
    metadata = {
        "source_id": record.source_id,
        "source_type": record.source_type.value,
        "source_reference": record.source_reference,
        "title": record.title,
        "topic": record.topic,
        "captured_at": record.captured_at,
        "freshness": record.freshness.value,
        "authority": record.authority.value,
        "confidence": record.confidence.value,
        "sensitivity": record.sensitivity.value,
        "user_scope": record.user_scope,
        "contradicted_by": ",".join(record.contradicted_by),
        "safe_explanation": record.safe_explanation,
    }
    lines = ["---", *(f"{key}: {value}" for key, value in metadata.items()), "---", "", record.content, ""]
    return "\n".join(lines)


def write_source_fixture_markdown(source_dir: str | Path) -> tuple[Path, ...]:
    target = Path(source_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = []
    for record in build_source_fixture_records():
        path = target / f"{record.source_id}.md"
        path.write_text(render_markdown_source(record), encoding="utf-8")
        paths.append(path)
    return tuple(paths)


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("source_front_matter_required")
    parts = text.split("---\n", 2)
    if len(parts) != 3:
        raise ValueError("source_front_matter_required")
    metadata_text, content = parts[1], parts[2]
    metadata = {}
    for raw_line in metadata_text.splitlines():
        if not raw_line.strip():
            continue
        if ":" not in raw_line:
            raise ValueError("source_metadata_malformed")
        key, value = raw_line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata, content


def _required(metadata: dict[str, str], key: str) -> str:
    value = metadata.get(key, "")
    if not value:
        raise ValueError(f"source_metadata_missing:{key}")
    return value


def _split_ids(value: str) -> tuple[str, ...]:
    return tuple(item for item in (part.strip() for part in value.split(",")) if item)


def source_terms(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.lower()))
