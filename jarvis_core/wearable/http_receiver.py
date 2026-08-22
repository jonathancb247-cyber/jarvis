"""Validation-only HTTP adapter for Wear OS presence heartbeats."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Type

from .presence_receiver import PresencePayloadStatus, WearablePresenceReceiver


PRESENCE_PATH = "/wearable/presence"
STATUS_PATH = "/wearable/status"


def build_presence_http_handler(receiver: WearablePresenceReceiver) -> Type[BaseHTTPRequestHandler]:
    class WearablePresenceHandler(BaseHTTPRequestHandler):
        server_version = "JarvisOSWearablePresence/0.1"

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path != PRESENCE_PATH:
                self._send_json(404, {"ok": False, "reason": "not_found"})
                return

            length = self._content_length()
            if length is None or length > receiver.max_payload_bytes:
                self._drain(length)
                self._send_json(413, {"ok": False, "reason": "payload_too_large"})
                return

            result = receiver.receive_payload(self.rfile.read(length))
            status = 202 if result.status == PresencePayloadStatus.ACCEPTED else 400
            self._send_json(status, {"ok": result.accepted, "reason": result.reason})

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path != STATUS_PATH:
                self._send_json(404, {"ok": False, "reason": "not_found"})
                return

            projection = receiver.projection()
            self._send_json(
                200,
                {
                    "wearable_id": projection.wearable_id,
                    "connection_state": projection.connection_state.value,
                    "capability_status": projection.capability_status.value,
                    "freshness": projection.freshness.value,
                    "confidence": projection.confidence.value,
                    "sensitivity": projection.sensitivity.value,
                    "user_scope": projection.user_scope,
                    "safe_explanation": projection.safe_explanation,
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _content_length(self) -> int | None:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return None
            try:
                length = int(raw_length)
            except ValueError:
                return None
            if length < 0:
                return None
            return length

        def _drain(self, length: int | None) -> None:
            if length is not None and length > 0:
                self.rfile.read(min(length, receiver.max_payload_bytes))

        def _send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return WearablePresenceHandler


def build_presence_http_server(
    *,
    host: str,
    port: int,
    receiver: WearablePresenceReceiver,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), build_presence_http_handler(receiver))
