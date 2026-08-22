"""Map detached wearable projections into cognitive evidence."""

from __future__ import annotations

from jarvis_core.cognitive.models import EvidenceOrigin, Freshness, Relevance, Signal

from .models import WearableConnectionState, WearablePresenceProjection


def wearable_projection_to_signal(projection: WearablePresenceProjection) -> Signal:
    if projection.connection_state is WearableConnectionState.CONNECTED:
        return Signal(
            kind="watch_connected",
            confidence=projection.confidence,
            freshness=Freshness.FRESH,
            provenance=projection.provenance,
            origin=EvidenceOrigin.WEARABLE,
            sensitivity=projection.sensitivity,
            user_scope=projection.user_scope,
            relevance=Relevance.MEDIUM,
            safe_explanation=(
                "Watch connection signal is currently available. "
                "This does not prove user presence, identity, watch wearing, wakefulness, health, availability, or location."
            ),
        )

    if projection.connection_state is WearableConnectionState.DISCONNECTED:
        return Signal(
            kind="watch_unavailable",
            confidence=projection.confidence,
            freshness=projection.freshness,
            provenance=projection.provenance,
            origin=EvidenceOrigin.WEARABLE,
            sensitivity=projection.sensitivity,
            user_scope=projection.user_scope,
            relevance=Relevance.LOW,
            safe_explanation="Wearable signal is unavailable; no user absence or availability should be inferred.",
        )

    return Signal(
        kind="watch_unknown_or_stale",
        confidence=projection.confidence,
        freshness=Freshness.STALE,
        provenance=projection.provenance,
        origin=EvidenceOrigin.WEARABLE,
        sensitivity=projection.sensitivity,
        user_scope=projection.user_scope,
        relevance=Relevance.LOW,
        safe_explanation="Wearable signal is unknown or stale; context confidence is reduced.",
    )
