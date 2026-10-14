"""Wearable boundary helpers for deterministic local diagnostics."""

from .fixtures import build_wearable_presence_fixtures
from .mapping import wearable_projection_to_signal
from .models import (
    WearableCapabilityStatus,
    WearableConnectionState,
    WearablePresenceProjection,
)
from .presence_receiver import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_MAX_PAYLOAD_BYTES,
    DEFAULT_STALE_TIMEOUT_SECONDS,
    DEFAULT_WEARABLE_ID,
    PresencePayloadResult,
    WearablePresenceReceiver,
    presence_payload,
)

__all__ = [
    "WearableCapabilityStatus",
    "WearableConnectionState",
    "WearablePresenceProjection",
    "WearablePresenceReceiver",
    "PresencePayloadResult",
    "DEFAULT_HEARTBEAT_INTERVAL_SECONDS",
    "DEFAULT_MAX_PAYLOAD_BYTES",
    "DEFAULT_STALE_TIMEOUT_SECONDS",
    "DEFAULT_WEARABLE_ID",
    "build_wearable_presence_fixtures",
    "presence_payload",
    "wearable_projection_to_signal",
]
