"""Immutable value objects for deterministic in-memory knowledge retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KnowledgeKind(str, Enum):
    EXPLICIT_USER_FACT = "explicit_user_fact"
    APPROVED_PREFERENCE = "approved_preference"
    PROJECT_DECISION = "project_decision"
    PROJECT_STATUS = "project_status"
    CORRECTION = "correction"
    SOURCE_REFERENCE = "source_reference"


class KnowledgeFreshness(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    HISTORICAL = "historical"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"


class KnowledgeConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXPLICIT = "explicit"


class KnowledgeOrigin(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class KnowledgeSensitivity(str, Enum):
    ORDINARY = "ordinary"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class RetrievalStatus(str, Enum):
    FOUND = "found"
    UNKNOWN = "unknown"
    CONTRADICTED = "contradicted"


@dataclass(frozen=True)
class KnowledgeItem:
    knowledge_id: str
    kind: KnowledgeKind
    topic: str
    summary: str
    source_type: str
    source_reference: str
    freshness: KnowledgeFreshness
    confidence: KnowledgeConfidence
    origin: KnowledgeOrigin
    sensitivity: KnowledgeSensitivity
    user_scope: str
    captured_at: str
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    contradicted_by: tuple[str, ...] = ()
    safe_explanation: str = ""


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    status: RetrievalStatus
    answer: str | None
    selected_evidence: KnowledgeItem | None
    supporting_evidence: tuple[KnowledgeItem, ...]
    conflicting_evidence: tuple[KnowledgeItem, ...]
    superseded_evidence: tuple[KnowledgeItem, ...]
    provenance: tuple[str, ...]
    freshness: KnowledgeFreshness | None
    confidence: KnowledgeConfidence | None
    safe_explanation: str

    @property
    def has_contradiction(self) -> bool:
        return bool(self.conflicting_evidence) or self.status is RetrievalStatus.CONTRADICTED
