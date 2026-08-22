"""Deterministic fake wearable fixtures for CI-safe diagnostics."""

from __future__ import annotations

from jarvis_core.cognitive.models import ConfidenceBand, Freshness

from .models import WearableCapabilityStatus, WearableConnectionState, WearablePresenceProjection


def build_wearable_presence_fixtures() -> tuple[WearablePresenceProjection, ...]:
    return (
        WearablePresenceProjection.create(
            wearable_id="pixel_watch_fake",
            connection_state=WearableConnectionState.CONNECTED,
            capability_status=WearableCapabilityStatus.SUPPORTED,
            freshness=Freshness.FRESH,
            confidence=ConfidenceBand.MEDIUM,
            safe_explanation="A fake Wear OS probe appears connected to the local wearable boundary.",
        ),
        WearablePresenceProjection.create(
            wearable_id="pixel_watch_fake",
            connection_state=WearableConnectionState.DISCONNECTED,
            capability_status=WearableCapabilityStatus.UNAVAILABLE,
            freshness=Freshness.FRESH,
            confidence=ConfidenceBand.MEDIUM,
            safe_explanation="The fake Wear OS probe is disconnected from the local wearable boundary.",
        ),
        WearablePresenceProjection.create(
            wearable_id="pixel_watch_fake",
            connection_state=WearableConnectionState.UNKNOWN,
            capability_status=WearableCapabilityStatus.UNKNOWN,
            freshness=Freshness.STALE,
            confidence=ConfidenceBand.LOW,
            safe_explanation="The fake Wear OS probe state is unknown.",
        ),
        WearablePresenceProjection.create(
            wearable_id="pixel_watch_fake",
            connection_state=WearableConnectionState.STALE,
            capability_status=WearableCapabilityStatus.PARTIALLY_SUPPORTED,
            freshness=Freshness.STALE,
            confidence=ConfidenceBand.LOW,
            safe_explanation="Prior fake Wear OS probe evidence exists but is not current.",
        ),
    )
