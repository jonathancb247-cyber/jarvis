"""Read-only semantic signal mappers for cognitive diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .models import ConfidenceBand, EvidenceOrigin, Freshness, Relevance, Signal


class DeviceStateProjectionStatus(str, Enum):
    UNKNOWN = "unknown"
    KNOWN = "known"
    STALE = "stale"


@dataclass(frozen=True)
class SafeSemanticProperty:
    key: str
    value: str | int | float | bool | None


@dataclass(frozen=True)
class DeviceStateSemanticProjection:
    device_id: str
    status: DeviceStateProjectionStatus
    is_current: bool
    safe_properties: tuple[SafeSemanticProperty, ...] = ()

    @classmethod
    def from_mapping(
        cls,
        *,
        device_id: str,
        status: str | DeviceStateProjectionStatus,
        is_current: bool,
        safe_properties: Mapping[str, object] | None = None,
    ) -> "DeviceStateSemanticProjection":
        return cls(
            device_id=device_id,
            status=DeviceStateProjectionStatus(status),
            is_current=is_current,
            safe_properties=_safe_properties(safe_properties or {}),
        )


def device_state_projection_to_signal(projection: DeviceStateSemanticProjection) -> Signal:
    if projection.status is DeviceStateProjectionStatus.KNOWN and projection.is_current:
        return Signal(
            kind="current_device_state",
            confidence=ConfidenceBand.HIGH,
            freshness=Freshness.FRESH,
            provenance=EvidenceOrigin.DEVICE_STATE.value,
            origin=EvidenceOrigin.DEVICE_STATE,
            relevance=Relevance.MEDIUM,
            safe_explanation=f"Current semantic state evidence is available for {projection.device_id}.",
        )
    if projection.status is DeviceStateProjectionStatus.STALE or (
        projection.status is DeviceStateProjectionStatus.KNOWN and not projection.is_current
    ):
        summary = _property_summary(projection.safe_properties)
        suffix = f" Last safe semantic summary: {summary}." if summary else ""
        return Signal(
            kind="stale_device_state",
            confidence=ConfidenceBand.HIGH,
            freshness=Freshness.STALE,
            provenance=EvidenceOrigin.DEVICE_STATE.value,
            origin=EvidenceOrigin.DEVICE_STATE,
            relevance=Relevance.HIGH,
            safe_explanation=f"Prior semantic state exists for {projection.device_id}, but it is not current.{suffix}",
        )
    return Signal(
        kind="unknown_device_state",
        confidence=ConfidenceBand.LOW,
        freshness=Freshness.STALE,
        provenance=EvidenceOrigin.DEVICE_STATE.value,
        origin=EvidenceOrigin.DEVICE_STATE,
        relevance=Relevance.MEDIUM,
        safe_explanation=f"Insufficient current semantic device evidence is available for {projection.device_id}.",
    )


def _safe_properties(properties: Mapping[str, object]) -> tuple[SafeSemanticProperty, ...]:
    normalized: list[SafeSemanticProperty] = []
    for key in sorted(properties):
        if len(normalized) >= 8:
            break
        if not _is_safe_property_key(key):
            continue
        value = properties[key]
        if not _is_safe_property_value(value):
            continue
        normalized.append(SafeSemanticProperty(key=key, value=_normalize_value(value)))
    return tuple(normalized)


def _is_safe_property_key(key: str) -> bool:
    if not key or len(key) > 48:
        return False
    lowered = key.lower()
    blocked = (
        "base_url",
        "url",
        "ip",
        "host",
        "port",
        "transport",
        "driver",
        "header",
        "broker",
        "topic",
        "sock" + "et",
        "error",
        "exception",
        "provider",
        "runtime",
        "payload",
        "path",
    )
    if any(token in lowered for token in blocked):
        return False
    return all(character.isalnum() or character in "._-" for character in key)


def _is_safe_property_value(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _normalize_value(value: object) -> str | int | float | bool | None:
    if isinstance(value, str):
        return value[:80]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    raise TypeError("Unsupported safe semantic property value.")


def _property_summary(properties: tuple[SafeSemanticProperty, ...]) -> str:
    parts = [f"{property.key}={property.value}" for property in properties]
    return ", ".join(parts)
