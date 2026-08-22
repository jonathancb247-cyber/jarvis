"""Detached wearable status models for the fake-first presence signal."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from jarvis_core.cognitive.models import ConfidenceBand, Freshness, Sensitivity


class WearableConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"
    STALE = "stale"


class WearableCapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNAVAILABLE = "unavailable"
    BLOCKED_BY_PLATFORM = "blocked_by_platform"
    REQUIRES_COMPANION = "requires_companion"
    REQUIRES_PERMISSION = "requires_permission"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class WearablePresenceProjection:
    wearable_id: str
    connection_state: WearableConnectionState
    capability_status: WearableCapabilityStatus
    provenance: str
    freshness: Freshness
    confidence: ConfidenceBand
    sensitivity: Sensitivity
    user_scope: str
    safe_explanation: str

    @classmethod
    def create(
        cls,
        *,
        wearable_id: str,
        connection_state: str | WearableConnectionState,
        capability_status: str | WearableCapabilityStatus,
        freshness: Freshness,
        confidence: ConfidenceBand,
        user_scope: str = "primary_user",
        safe_explanation: str,
    ) -> "WearablePresenceProjection":
        return cls(
            wearable_id=wearable_id,
            connection_state=WearableConnectionState(connection_state),
            capability_status=WearableCapabilityStatus(capability_status),
            provenance="wearable",
            freshness=freshness,
            confidence=confidence,
            sensitivity=Sensitivity.PERSONAL,
            user_scope=user_scope,
            safe_explanation=safe_explanation,
        )
