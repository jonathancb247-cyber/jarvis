"""Lab-only HTTP transport for a future Android Gemma companion bridge.

The bridge is intentionally cleartext and restricted to local/private network
destinations.  Public Internet hosts are rejected at configuration time.
This boundary must not be relaxed without explicit security approval.
"""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import json
import socket
from typing import Callable

from jarvis_core.ai.contracts import (
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
)
from jarvis_core.ai.gemma_local import (
    GemmaLocalProviderError,
    GemmaLocalResponse,
)


GEMMA_ANDROID_BRIDGE_GENERATE_PATH = "/generate"
DEFAULT_ANDROID_BRIDGE_PORT = 8767


@dataclass(frozen=True)
class GemmaAndroidBridgeConfig:
    """Explicit lab-only Android bridge endpoint configuration."""

    host: str
    port: int = DEFAULT_ANDROID_BRIDGE_PORT

    def __post_init__(self) -> None:
        _require_host(self.host)
        _require_int(self.port, "port", minimum=1, maximum=65535)


class GemmaAndroidBridgeTransport:
    """HTTP transport for a future JarvisOS Android companion app.

    Minimal companion contract:
    - request: POST /generate with application/json body equal to the
      GemmaLocalAIProvider request object;
    - response: HTTP 2xx with application/json body containing exactly one
      provider envelope understood by GemmaLocalAIProvider, such as an
      AIActionPlan object, {"plan": {...}}, {"output_text": "..."} or
      {"tool_calls": [...]}.

    An optional [on_response] observer is a lab/evaluation hook only: when set,
    it is called with the HTTP status and bounded raw response body for every
    response (2xx and errors) so evaluation tooling can count Android-side JSON
    rejections without loosening any error normalization. The default path is
    unchanged and never reads a response body before status/Content-Length
    validation.
    """

    def __init__(
        self,
        config: GemmaAndroidBridgeConfig,
        *,
        on_response: Callable[[int, bytes], None] | None = None,
    ) -> None:
        self.config = config
        self.on_response = on_response

    def generate(
        self,
        request: dict[str, object],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> GemmaLocalResponse:
        _require_int(timeout_seconds, "timeout_seconds", minimum=1, maximum=180)
        _require_int(
            max_response_bytes,
            "max_response_bytes",
            minimum=1024,
            maximum=512 * 1024,
        )
        try:
            body = json.dumps(
                request,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR) from error

        connection = http.client.HTTPConnection(
            self.config.host,
            port=self.config.port,
            timeout=timeout_seconds,
        )
        try:
            connection.request(
                "POST",
                GEMMA_ANDROID_BRIDGE_GENERATE_PATH,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            status = response.status
            headers = response.getheaders()
            raw = None
            if self.on_response is not None:
                raw = response.read(max_response_bytes + 1)
                self.on_response(status, raw)
            _raise_for_status(status)
            _require_json_content(headers)
            _reject_oversized_content_length(headers, max_response_bytes)
            if raw is None:
                raw = response.read(max_response_bytes + 1)
            return _parse_response(raw, max_response_bytes)
        except TimeoutError as error:
            raise GemmaLocalProviderError(AI_PROVIDER_TIMEOUT) from error
        except (OSError, http.client.HTTPException, socket.timeout) as error:
            raise GemmaLocalProviderError(AI_PROVIDER_UNAVAILABLE) from error
        finally:
            connection.close()


def _raise_for_status(status: int) -> None:
    if 200 <= status < 300:
        return
    if status == 408:
        raise GemmaLocalProviderError(AI_PROVIDER_TIMEOUT)
    if status == 413:
        raise GemmaLocalProviderError(AI_RESPONSE_TOO_LARGE)
    if 500 <= status < 600:
        raise GemmaLocalProviderError(AI_PROVIDER_UNAVAILABLE)
    raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR)


def _require_json_content(headers: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> None:
    for key, value in headers:
        if key.lower() == "content-type":
            content_type = value.split(";", 1)[0].strip().lower()
            if content_type == "application/json":
                return
            raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR)


def _reject_oversized_content_length(
    headers: list[tuple[str, str]] | tuple[tuple[str, str], ...],
    max_response_bytes: int,
) -> None:
    values = [value.strip() for key, value in headers if key.lower() == "content-length"]
    if not values:
        return
    if len(values) > 1:
        raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    try:
        content_length = int(values[0])
    except ValueError as error:
        raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR) from error
    if content_length < 0:
        raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    if content_length > max_response_bytes:
        raise GemmaLocalProviderError(AI_RESPONSE_TOO_LARGE)


def _parse_response(raw: bytes, max_response_bytes: int) -> GemmaLocalResponse:
    if len(raw) > max_response_bytes:
        raise GemmaLocalProviderError(AI_RESPONSE_TOO_LARGE)
    if not raw:
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID) from error
    if not isinstance(parsed, dict):
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
    return GemmaLocalResponse(parsed, len(raw))


def _require_host(host: str) -> None:
    if not isinstance(host, str) or not host.strip():
        raise ValueError("Gemma Android bridge host is required")
    if len(host) > 255:
        raise ValueError("Gemma Android bridge host is invalid")
    forbidden = ("://", "/", "\\", "?", "#", "@", " ", "\t", "\r", "\n")
    if any(token in host for token in forbidden):
        raise ValueError("Gemma Android bridge host is invalid")
    if not _is_local_host(host):
        raise ValueError(
            "Gemma Android bridge host must be a local/private address; "
            "public Internet destinations are not allowed"
        )


def _is_local_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        addr = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv4Address):
        return (
            addr.is_loopback
            or addr.is_private
            or addr.is_link_local
        )
    if isinstance(addr, ipaddress.IPv6Address):
        return addr.is_loopback or addr.is_link_local
    return False


def _require_int(value: int, label: str, *, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"Gemma Android bridge {label} is invalid")


__all__ = [
    "DEFAULT_ANDROID_BRIDGE_PORT",
    "GEMMA_ANDROID_BRIDGE_GENERATE_PATH",
    "GemmaAndroidBridgeConfig",
    "GemmaAndroidBridgeTransport",
]
