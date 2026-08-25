"""Deterministic in-memory retrieval for Second Brain Phase 1."""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from .fixtures import build_seed_knowledge
from .models import (
    KnowledgeConfidence,
    KnowledgeFreshness,
    KnowledgeItem,
    KnowledgeKind,
    RetrievalResult,
    RetrievalStatus,
)


_STATUS_RANK = {
    KnowledgeFreshness.CURRENT: 0,
    KnowledgeFreshness.STALE: 1,
    KnowledgeFreshness.HISTORICAL: 2,
    KnowledgeFreshness.SUPERSEDED: 3,
    KnowledgeFreshness.CONTRADICTED: 4,
}

_CONFIDENCE_RANK = {
    KnowledgeConfidence.EXPLICIT: 0,
    KnowledgeConfidence.HIGH: 1,
    KnowledgeConfidence.MEDIUM: 2,
    KnowledgeConfidence.LOW: 3,
}

_SOURCE_RANK = {
    "explicit_user_correction": 0,
    "github_project_state": 1,
    "explicit_user_preference": 2,
    "explicit_user_fact": 3,
    "historical_project_snapshot": 4,
    "stale_note": 5,
    "source_reference": 6,
    "provider_like_synthetic": 9,
}

_STOP_TERMS = {
    "about",
    "decide",
    "fact",
    "leave",
    "lookup",
    "phase",
    "status",
    "what",
    "where",
    "work",
}

_SINGLE_TERM_TOPICS = {"mqtt"}


class InMemoryKnowledgeRetriever:
    def __init__(self, items: Sequence[KnowledgeItem] | None = None):
        self._items = tuple(items if items is not None else build_seed_knowledge())

    @property
    def items(self) -> tuple[KnowledgeItem, ...]:
        return self._items

    def retrieve(self, query: str) -> RetrievalResult:
        normalized_query = _normalize(query)
        matches = self._matches(normalized_query)
        if not matches:
            return RetrievalResult(
                query=query,
                status=RetrievalStatus.UNKNOWN,
                answer=None,
                selected_evidence=None,
                supporting_evidence=(),
                conflicting_evidence=(),
                superseded_evidence=(),
                provenance=(),
                freshness=None,
                confidence=None,
                safe_explanation="No matching approved or source-backed knowledge was found; no answer was fabricated.",
            )

        ordered = tuple(sorted(matches, key=lambda match: (_rank_key(match[0]), match[1])))
        selected = ordered[0][0]
        ordered_items = tuple(match[0] for match in ordered)
        conflicts = _conflicts(selected, ordered_items)
        superseded = _superseded_for(selected, ordered_items, self._items)

        if conflicts and _rank_strength(conflicts[0]) == _rank_strength(selected):
            return RetrievalResult(
                query=query,
                status=RetrievalStatus.CONTRADICTED,
                answer=None,
                selected_evidence=None,
                supporting_evidence=(),
                conflicting_evidence=tuple(sorted({*conflicts, selected}, key=lambda item: item.knowledge_id)),
                superseded_evidence=superseded,
                provenance=tuple(_provenance(item) for item in sorted({*conflicts, selected}, key=lambda item: item.knowledge_id)),
                freshness=KnowledgeFreshness.CONTRADICTED,
                confidence=KnowledgeConfidence.LOW,
                safe_explanation="Matching evidence has equal-strength contradictions; retrieval refused to invent a single truth.",
            )

        support = tuple(item for item in ordered_items if item is selected or item.knowledge_id in selected.supersedes)
        explanation = selected.safe_explanation
        if conflicts:
            explanation = f"{explanation} Conflicting evidence is retained for review."
        if superseded:
            explanation = f"{explanation} Superseded evidence is shown as historical, not co-current."

        return RetrievalResult(
            query=query,
            status=RetrievalStatus.FOUND,
            answer=selected.summary,
            selected_evidence=selected,
            supporting_evidence=support,
            conflicting_evidence=conflicts,
            superseded_evidence=superseded,
            provenance=tuple(_provenance(item) for item in support),
            freshness=selected.freshness,
            confidence=selected.confidence,
            safe_explanation=explanation,
        )

    def _matches(self, normalized_query: str) -> tuple[tuple[KnowledgeItem, int], ...]:
        query_terms = set(_terms(normalized_query))
        matches = []
        for item in self._items:
            if normalized_query == _normalize(item.knowledge_id):
                matches.append((item, 100))
                continue
            haystack = " ".join((item.knowledge_id, item.kind.value, item.topic, item.summary, item.source_reference))
            haystack_terms = set(_terms(_normalize(haystack)))
            score = _overlap_score(query_terms, haystack_terms)
            if score >= 2 or (score == 1 and query_terms.intersection(_SINGLE_TERM_TOPICS)):
                matches.append((item, -score))
        return tuple(matches)


def build_demo_queries() -> tuple[str, ...]:
    return (
        "Where did I leave the Pixel Watch work?",
        "What did we decide about MQTT?",
        "approved preference lookup",
        "synthetic workspace color",
        "ambiguous fixture",
        "unknown fact",
    )


def run_demo_queries(retriever: InMemoryKnowledgeRetriever | None = None) -> tuple[RetrievalResult, ...]:
    engine = retriever or InMemoryKnowledgeRetriever()
    return tuple(engine.retrieve(query) for query in build_demo_queries())


def _rank_key(item: KnowledgeItem) -> tuple[int, int, int, str]:
    return (*_rank_strength(item), item.knowledge_id)


def _rank_strength(item: KnowledgeItem) -> tuple[int, int, int]:
    return (
        _STATUS_RANK[item.freshness],
        _SOURCE_RANK.get(item.source_type, 8),
        _CONFIDENCE_RANK[item.confidence],
    )


def _normalize(value: str) -> str:
    return " ".join(_terms(value))


def _terms(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.lower()))


def _overlap_score(query_terms: set[str], haystack_terms: set[str]) -> int:
    meaningful = {term for term in query_terms if len(term) >= 4 and term not in _STOP_TERMS}
    return len(meaningful.intersection(haystack_terms))


def _conflicts(selected: KnowledgeItem, ordered: Sequence[KnowledgeItem]) -> tuple[KnowledgeItem, ...]:
    conflict_ids = set(selected.contradicted_by)
    conflicts = [item for item in ordered if item.knowledge_id in conflict_ids]
    for item in ordered:
        if selected.knowledge_id in item.contradicted_by and item not in conflicts:
            conflicts.append(item)
    return tuple(sorted(conflicts, key=_rank_key))


def _superseded_for(
    selected: KnowledgeItem,
    ordered: Sequence[KnowledgeItem],
    all_items: Iterable[KnowledgeItem],
) -> tuple[KnowledgeItem, ...]:
    superseded_ids = set(selected.supersedes)
    superseded = [item for item in ordered if item.knowledge_id in superseded_ids]
    for item in all_items:
        if item.knowledge_id in superseded_ids and item not in superseded:
            superseded.append(item)
    return tuple(sorted(superseded, key=lambda item: item.knowledge_id))


def _provenance(item: KnowledgeItem) -> str:
    return f"{item.source_type}:{item.source_reference}"
