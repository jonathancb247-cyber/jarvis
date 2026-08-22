"""Wearable boundary helpers for deterministic local diagnostics."""

from .fixtures import build_wearable_presence_fixtures
from .mapping import wearable_projection_to_signal
from .models import (
    WearableCapabilityStatus,
    WearableConnectionState,
    WearablePresenceProjection,
)

__all__ = [
    "WearableCapabilityStatus",
    "WearableConnectionState",
    "WearablePresenceProjection",
    "build_wearable_presence_fixtures",
    "wearable_projection_to_signal",
]
