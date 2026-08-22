"""Local HTTP presence receiver for Wear OS validation.

This module belongs to the wearable boundary. It observes a bounded local
heartbeat and creates detached wearable projections. It does not integrate with
Runtime, DeviceState, API, Dashboard, persistence, providers, or hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from time import monotonic
from typing import Callable

from jarvis_core.cognitive.models import ConfidenceBand, Freshness

from .models import WearableCapabilityStatus, WearableConnectionState, WearablePresenceProjection


Clock = Callable[[], float]


DEFAULT_WEARABLE_ID = "pixel_watch_probe"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0
DEFAULT_STALE_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_PAYLOAD_BYTES = 256


class PresencePayloadStatus:
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PresencePayloadResult:
    status: str
    reason: str

    @property
    def accepted(self) -> bool:
        return self.status == PresencePayloadStatus.ACCEPTED


class WearablePresenceReceiver:
    """Normalizes validation heartbeats into detached wearable projections."""

    def __init__(
        self,
        *,
        expected_wearable_id: str = DEFAULT_WEARABLE_ID,
        stale_timeout_seconds: float = DEFAULT_STALE_TIMEOUT_SECONDS,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        clock: Clock = monotonic,
    ) -> None:
        if not expected_wearable_id:
            raise ValueError("expected_wearable_id is required")
        if stale_timeout_seconds <= 0:
            raise ValueError("stale_timeout_seconds must be positive")
        if max_payload_bytes <= 0:
            raise ValueError("max_payload_bytes must be positive")
        self._expected_wearable_id = expected_wearable_id
        self._stale_timeout_seconds = stale_timeout_seconds
        self._max_payload_bytes = max_payload_bytes
        self._clock = clock
        self._last_connected_at: float | None = None
        self._explicit_disconnect_at: float | None = None

    @property
    def expected_wearable_id(self) -> str:
        return self._expected_wearable_id

    @property
    def stale_timeout_seconds(self) -> float:
        return self._stale_timeout_seconds

    @property
    def max_payload_bytes(self) -> int:
        return self._max_payload_bytes

    def receive_payload(self, payload: bytes) -> PresencePayloadResult:
        if len(payload) > self._max_payload_bytes:
            return PresencePayloadResult(PresencePayloadStatus.REJECTED, "payload_too_large")

        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return PresencePayloadResult(PresencePayloadStatus.REJECTED, "invalid_json")

        if not isinstance(data, dict):
            return PresencePayloadResult(PresencePayloadStatus.REJECTED, "invalid_payload")

        allowed_fields = {"wearable_id", "state"}
        if set(data) != allowed_fields:
            return PresencePayloadResult(PresencePayloadStatus.REJECTED, "unsupported_fields")

        wearable_id = data.get("wearable_id")
        state = data.get("state")
        if wearable_id != self._expected_wearable_id:
            return PresencePayloadResult(PresencePayloadStatus.REJECTED, "unsupported_wearable_id")
        if state == WearableConnectionState.CONNECTED.value:
            self._last_connected_at = self._clock()
            self._explicit_disconnect_at = None
            return PresencePayloadResult(PresencePayloadStatus.ACCEPTED, "connected")
        if state == WearableConnectionState.DISCONNECTED.value:
            self._explicit_disconnect_at = self._clock()
            return PresencePayloadResult(PresencePayloadStatus.ACCEPTED, "disconnected")
        return PresencePayloadResult(PresencePayloadStatus.REJECTED, "unsupported_state")

    def projection(self) -> WearablePresenceProjection:
        now = self._clock()
        if self._explicit_disconnect_at is not None and (
            self._last_connected_at is None or self._explicit_disconnect_at >= self._last_connected_at
        ):
            return WearablePresenceProjection.create(
                wearable_id=self._expected_wearable_id,
                connection_state=WearableConnectionState.DISCONNECTED,
                capability_status=WearableCapabilityStatus.UNAVAILABLE,
                freshness=Freshness.FRESH,
                confidence=ConfidenceBand.MEDIUM,
                safe_explanation="The Wear OS probe explicitly disconnected from the local wearable boundary.",
            )

        if self._last_connected_at is None:
            return WearablePresenceProjection.create(
                wearable_id=self._expected_wearable_id,
                connection_state=WearableConnectionState.UNKNOWN,
                capability_status=WearableCapabilityStatus.UNKNOWN,
                freshness=Freshness.STALE,
                confidence=ConfidenceBand.LOW,
                safe_explanation="No valid Wear OS heartbeat has been observed by the local wearable boundary.",
            )

        age = now - self._last_connected_at
        if age <= self._stale_timeout_seconds:
            return WearablePresenceProjection.create(
                wearable_id=self._expected_wearable_id,
                connection_state=WearableConnectionState.CONNECTED,
                capability_status=WearableCapabilityStatus.SUPPORTED,
                freshness=Freshness.FRESH,
                confidence=ConfidenceBand.MEDIUM,
                safe_explanation=(
                    "A known Wear OS probe appears connected to the local wearable boundary. "
                    "This is connection evidence only."
                ),
            )

        return WearablePresenceProjection.create(
            wearable_id=self._expected_wearable_id,
            connection_state=WearableConnectionState.STALE,
            capability_status=WearableCapabilityStatus.PARTIALLY_SUPPORTED,
            freshness=Freshness.STALE,
            confidence=ConfidenceBand.LOW,
            safe_explanation="Prior Wear OS probe heartbeat evidence exists but is not current.",
        )


def presence_payload(*, wearable_id: str = DEFAULT_WEARABLE_ID, state: str = "connected") -> bytes:
    """Build a compact validation payload for tests and manual tooling."""

    return json.dumps(
        {"wearable_id": wearable_id, "state": state},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
