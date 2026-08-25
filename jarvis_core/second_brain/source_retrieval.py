"""Deterministic source-index retrieval for Second Brain Phase 3/4 slice."""

from __future__ import annotations

import json
from typing import Iterable, Sequence

from .models import KnowledgeConfidence, KnowledgeFreshness
from .sources import (
    IndexedSourceDocument,
    SourceAuthority,
    SourceRetrievalResult,
    SourceRetrievalStatus,
    source_terms,
)


_FRESHNESS_RANK = {
    KnowledgeFreshness.CURRENT: 0,
    KnowledgeFreshness.STALE: 1,
    KnowledgeFreshness.HISTORICAL: 2,
    KnowledgeFreshness.SUPERSEDED: 3,
    KnowledgeFreshness.CONTRADICTED: 4,
}

_AUTHORITY_RANK = {
    SourceAuthority.PROJECT_STATE: 0,
    SourceAuthority.DESIGN_ADR: 1,
    SourceAuthority.FIXTURE: 2,
    SourceAuthority.NOTE: 3,
    SourceAuthority.HISTORICAL: 4,
}

_CONFIDENCE_RANK = {
    KnowledgeConfidence.EXPLICIT: 0,
    KnowledgeConfidence.HIGH: 1,
    KnowledgeConfidence.MEDIUM: 2,
    KnowledgeConfidence.LOW: 3,
}

_STOP_TERMS = {
    "about",
    "current",
    "document",
    "fixture",
    "phase",
    "project",
    "source",
    "status",
    "what",
}


class DeterministicSemanticScorer:
    """Fake semantic scorer for deterministic tests.

    It is not a model-backed scorer, does not call providers, and does not decide
    truth. It only adds a bounded synonym-style relevance signal.
    """

    _ALIASES = {
        "durable": {"storage", "persistence"},
        "index": {"source", "document", "retrieval"},
        "watch": {"wearable", "pixel"},
        "broker": {"mqtt", "mosquitto"},
    }

    def score(self, query_terms: set[str], document_terms: set[str]) -> int:
        score = 0
        for term in query_terms:
            aliases = self._ALIASES.get(term, set())
            if aliases.intersection(document_terms):
                score += 1
        return score


class SourceHybridRetriever:
    def __init__(
        self,
        documents: Sequence[IndexedSourceDocument],
        *,
        semantic_scorer: DeterministicSemanticScorer | None = None,
    ):
        self._documents = tuple(documents)
        self._semantic_scorer = semantic_scorer or DeterministicSemanticScorer()

    @property
    def documents(self) -> tuple[IndexedSourceDocument, ...]:
        return self._documents

    def retrieve(self, query: str, *, user_scope: str | None = None) -> SourceRetrievalResult:
        query_terms = _meaningful_terms(query)
        matches = []
        for document in self._documents:
            if user_scope is not None and document.user_scope != user_scope:
                continue
            score = _lexical_score(query_terms, _document_terms(document))
            score += self._semantic_scorer.score(query_terms, _document_terms(document))
            if score > 0:
                matches.append((document, score))

        if not matches:
            return SourceRetrievalResult(
                query=query,
                status=SourceRetrievalStatus.UNKNOWN,
                answer=None,
                selected_document=None,
                supporting_documents=(),
                conflicting_documents=(),
                superseded_documents=(),
                provenance=(),
                freshness=None,
                confidence=None,
                relevance=0,
                safe_explanation="No matching indexed source was found; no source-backed answer was fabricated.",
            )

        ordered = tuple(sorted(matches, key=lambda match: (_rank_key(match[0], match[1]), match[0].document_id)))
        selected, relevance = ordered[0]
        ordered_docs = tuple(match[0] for match in ordered)
        conflicts = _conflicts(selected, ordered_docs)
        superseded = _superseded_for(selected, self._documents)

        if conflicts and _rank_strength(conflicts[0]) == _rank_strength(selected):
            conflict_set = tuple(sorted({selected, *conflicts}, key=lambda item: item.document_id))
            return SourceRetrievalResult(
                query=query,
                status=SourceRetrievalStatus.CONTRADICTED,
                answer=None,
                selected_document=None,
                supporting_documents=(),
                conflicting_documents=conflict_set,
                superseded_documents=superseded,
                provenance=tuple(_provenance(document) for document in conflict_set),
                freshness=KnowledgeFreshness.CONTRADICTED,
                confidence=KnowledgeConfidence.LOW,
                relevance=relevance,
                safe_explanation="Equal-strength current sources conflict; retrieval refused to invent truth.",
            )

        support = tuple(document for document in ordered_docs if document.document_id == selected.document_id)
        explanation = selected.safe_explanation
        if conflicts:
            explanation = f"{explanation} Conflicting source evidence is retained for review."
        if superseded:
            explanation = f"{explanation} Superseded source versions are historical, not co-current."

        return SourceRetrievalResult(
            query=query,
            status=SourceRetrievalStatus.FOUND,
            answer=_bounded_answer(selected),
            selected_document=selected,
            supporting_documents=support,
            conflicting_documents=conflicts,
            superseded_documents=superseded,
            provenance=tuple(_provenance(document) for document in support),
            freshness=selected.freshness,
            confidence=selected.confidence,
            relevance=relevance,
            safe_explanation=explanation,
        )


class SourceReportRenderer:
    def render_text(self, results: Iterable[SourceRetrievalResult]) -> str:
        lines = ["JarvisOS Second Brain Source Diagnostic Report", "mode: local_source_index", ""]
        for result in results:
            lines.extend(_source_result_lines(result))
            lines.append("")
        rendered = "\n".join(lines).rstrip() + "\n"
        _assert_safe_language(rendered)
        return rendered

    def render_json(self, results: Iterable[SourceRetrievalResult]) -> str:
        payload = {
            "mode": "local_source_index",
            "results": [_source_result_payload(result) for result in results],
        }
        rendered = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        _assert_safe_language(rendered)
        return rendered


def build_source_demo_queries() -> tuple[str, ...]:
    return (
        "Pixel Watch validation",
        "MQTT broker status",
        "Second Brain durable storage",
        "ambiguous source fixture",
        "unknown source topic",
    )


def run_source_demo_queries(retriever: SourceHybridRetriever) -> tuple[SourceRetrievalResult, ...]:
    return tuple(retriever.retrieve(query) for query in build_source_demo_queries())


def _rank_key(document: IndexedSourceDocument, score: int) -> tuple[int, int, int, int, str]:
    return (*_rank_strength(document), -score, document.document_id)


def _rank_strength(document: IndexedSourceDocument) -> tuple[int, int, int]:
    return (
        _FRESHNESS_RANK[document.freshness],
        _AUTHORITY_RANK[document.authority],
        _CONFIDENCE_RANK[document.confidence],
    )


def _meaningful_terms(value: str) -> set[str]:
    return {term for term in source_terms(value) if len(term) >= 4 and term not in _STOP_TERMS}


def _document_terms(document: IndexedSourceDocument) -> set[str]:
    return set(source_terms(" ".join((document.source_id, document.title, document.topic, document.content))))


def _lexical_score(query_terms: set[str], document_terms: set[str]) -> int:
    return len(query_terms.intersection(document_terms)) * 2


def _conflicts(
    selected: IndexedSourceDocument,
    ordered: Sequence[IndexedSourceDocument],
) -> tuple[IndexedSourceDocument, ...]:
    selected_sources = set(selected.contradicted_by)
    conflicts = [document for document in ordered if document.source_id in selected_sources]
    for document in ordered:
        if selected.source_id in document.contradicted_by and document not in conflicts:
            conflicts.append(document)
    return tuple(sorted(conflicts, key=lambda document: _rank_key(document, 0)))


def _superseded_for(
    selected: IndexedSourceDocument,
    all_documents: Iterable[IndexedSourceDocument],
) -> tuple[IndexedSourceDocument, ...]:
    superseded_ids = set(selected.supersedes)
    return tuple(
        sorted(
            (document for document in all_documents if document.document_id in superseded_ids),
            key=lambda document: document.document_id,
        )
    )


def _bounded_answer(document: IndexedSourceDocument) -> str:
    first_line = document.content.strip().splitlines()[0]
    return first_line[:240]


def _provenance(document: IndexedSourceDocument) -> str:
    return (
        f"{document.source_type.value}:{document.source_reference}:"
        f"{document.source_id}:{document.freshness.value}:{document.authority.value}"
    )


def _source_result_lines(result: SourceRetrievalResult) -> list[str]:
    return [
        f"- query: {result.query}",
        f"  status: {result.status.value}",
        f"  answer: {result.answer if result.answer is not None else 'unknown'}",
        f"  freshness: {result.freshness.value if result.freshness else 'unknown'}",
        f"  confidence: {result.confidence.value if result.confidence else 'unknown'}",
        f"  relevance: {result.relevance}",
        f"  provenance: {_format_tuple(result.provenance)}",
        f"  selected_source: {result.selected_document.document_id if result.selected_document else 'none'}",
        f"  superseded_sources: {_format_ids(result.superseded_documents)}",
        f"  conflicting_sources: {_format_ids(result.conflicting_documents)}",
        f"  explanation: {result.safe_explanation}",
    ]


def _source_result_payload(result: SourceRetrievalResult) -> dict[str, object]:
    return {
        "answer": result.answer,
        "confidence": result.confidence.value if result.confidence else None,
        "conflicting_sources": [_document_payload(document) for document in result.conflicting_documents],
        "freshness": result.freshness.value if result.freshness else None,
        "provenance": list(result.provenance),
        "query": result.query,
        "relevance": result.relevance,
        "safe_explanation": result.safe_explanation,
        "selected_source": _document_payload(result.selected_document) if result.selected_document else None,
        "status": result.status.value,
        "superseded_sources": [_document_payload(document) for document in result.superseded_documents],
        "supporting_sources": [_document_payload(document) for document in result.supporting_documents],
    }


def _document_payload(document: IndexedSourceDocument) -> dict[str, object]:
    return {
        "authority": document.authority.value,
        "confidence": document.confidence.value,
        "document_id": document.document_id,
        "freshness": document.freshness.value,
        "sensitivity": document.sensitivity.value,
        "source_id": document.source_id,
        "source_reference": document.source_reference,
        "source_type": document.source_type.value,
        "title": document.title,
        "topic": document.topic,
        "user_scope": document.user_scope,
    }


def _format_tuple(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _format_ids(documents: tuple[IndexedSourceDocument, ...]) -> str:
    return ", ".join(document.document_id for document in documents) if documents else "none"


def _assert_safe_language(text: str) -> None:
    lower = text.lower()
    for term in (
        "action queued",
        "action scheduled",
        "executed",
        "device changed",
        "notification sent",
        "rule created",
        "memory saved",
        "delegation granted",
        "command:",
    ):
        if term in lower:
            raise ValueError(f"Unsafe Second Brain source report wording: {term}")
