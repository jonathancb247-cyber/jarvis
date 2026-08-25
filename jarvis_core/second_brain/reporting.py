"""Local deterministic report rendering for Second Brain retrieval."""

from __future__ import annotations

import json
from typing import Iterable

from .models import KnowledgeItem, RetrievalResult


FORBIDDEN_REPORT_TERMS = (
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


class SecondBrainReportRenderer:
    def render_text(self, results: Iterable[RetrievalResult]) -> str:
        lines = ["JarvisOS Second Brain Diagnostic Report", "mode: deterministic_in_memory", ""]
        for result in results:
            lines.extend(_result_lines(result))
            lines.append("")
        rendered = "\n".join(lines).rstrip() + "\n"
        _assert_safe_language(rendered)
        return rendered

    def render_json(self, results: Iterable[RetrievalResult]) -> str:
        payload = {
            "mode": "deterministic_in_memory",
            "results": [_result_payload(result) for result in results],
        }
        rendered = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        _assert_safe_language(rendered)
        return rendered


def _result_lines(result: RetrievalResult) -> list[str]:
    lines = [
        f"- query: {result.query}",
        f"  status: {result.status.value}",
        f"  answer: {result.answer if result.answer is not None else 'unknown'}",
        f"  freshness: {result.freshness.value if result.freshness else 'unknown'}",
        f"  confidence: {result.confidence.value if result.confidence else 'unknown'}",
        f"  provenance: {_format_tuple(result.provenance)}",
        f"  selected_evidence: {result.selected_evidence.knowledge_id if result.selected_evidence else 'none'}",
        f"  superseded_evidence: {_format_ids(result.superseded_evidence)}",
        f"  conflicting_evidence: {_format_ids(result.conflicting_evidence)}",
        f"  explanation: {result.safe_explanation}",
    ]
    return lines


def _result_payload(result: RetrievalResult) -> dict[str, object]:
    return {
        "answer": result.answer,
        "confidence": result.confidence.value if result.confidence else None,
        "conflicting_evidence": [_item_payload(item) for item in result.conflicting_evidence],
        "freshness": result.freshness.value if result.freshness else None,
        "provenance": list(result.provenance),
        "query": result.query,
        "safe_explanation": result.safe_explanation,
        "selected_evidence": _item_payload(result.selected_evidence) if result.selected_evidence else None,
        "status": result.status.value,
        "superseded_evidence": [_item_payload(item) for item in result.superseded_evidence],
        "supporting_evidence": [_item_payload(item) for item in result.supporting_evidence],
    }


def _item_payload(item: KnowledgeItem) -> dict[str, object]:
    return {
        "captured_at": item.captured_at,
        "confidence": item.confidence.value,
        "freshness": item.freshness.value,
        "kind": item.kind.value,
        "knowledge_id": item.knowledge_id,
        "origin": item.origin.value,
        "sensitivity": item.sensitivity.value,
        "source_reference": item.source_reference,
        "source_type": item.source_type,
        "summary": item.summary,
        "superseded_by": list(item.superseded_by),
        "supersedes": list(item.supersedes),
        "topic": item.topic,
        "user_scope": item.user_scope,
    }


def _format_tuple(values: tuple[str, ...]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


def _format_ids(items: tuple[KnowledgeItem, ...]) -> str:
    if not items:
        return "none"
    return ", ".join(item.knowledge_id for item in items)


def _assert_safe_language(text: str) -> None:
    lower = text.lower()
    for term in FORBIDDEN_REPORT_TERMS:
        if term in lower:
            raise ValueError(f"Unsafe Second Brain report wording: {term}")
