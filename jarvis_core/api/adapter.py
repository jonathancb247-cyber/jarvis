"""Runtime-owned HTTP API adapter boundary."""

import json
from dataclasses import dataclass
from threading import Lock
from urllib.parse import unquote, urlparse

from jarvis_core.api import errors
from jarvis_core.api.interaction_service import InteractionAuth, LocalInteractionService
from jarvis_core.api.projections import ApiProjectionBuilder
from jarvis_core.api.validation import (
    MAX_REQUEST_BYTES,
    parse_json_body,
    validate_command_payload,
    validate_content_type,
    validate_device_id,
    validate_interaction_payload,
    validate_path,
)


API_SOURCE = "api"


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: dict
    headers: dict


class RuntimeApiAdapter:
    """Optional adapter exposing safe REST/JSON access to a Runtime."""

    def __init__(
        self,
        runtime,
        projection_builder,
        *,
        interaction_service=None,
        interaction_auth=None,
        interaction_only=False,
    ):
        if not callable(getattr(runtime, "handle_adapter_input", None)):
            raise TypeError("RuntimeApiAdapter requires a Runtime-like object")
        if not isinstance(projection_builder, ApiProjectionBuilder):
            raise TypeError("RuntimeApiAdapter requires an ApiProjectionBuilder")
        if interaction_service is not None:
            if not isinstance(interaction_service, LocalInteractionService):
                raise TypeError(
                    "RuntimeApiAdapter interaction_service must be a "
                    "LocalInteractionService"
                )
            if not isinstance(interaction_auth, InteractionAuth):
                raise TypeError(
                    "an interaction service requires an InteractionAuth"
                )
            if not interaction_only:
                raise TypeError(
                    "interactions may only be mounted in interaction_only mode"
                )
        if interaction_only and interaction_service is None:
            raise TypeError("interaction_only mode requires an interaction service")
        self._runtime = runtime
        self._projections = projection_builder
        self._interaction_service = interaction_service
        self._interaction_auth = interaction_auth
        self._interaction_only = bool(interaction_only)
        self._command_lock = Lock()

    def pre_authorize(self, method, path, headers=None):
        """Authenticate a body-carrying request before its body is consumed.

        Returns an :class:`ApiResponse` to short-circuit the request, or ``None``
        when the request may continue to body framing and dispatch. Only the
        authenticated interaction route requires this; every other route is left
        untouched so the existing contracts are unchanged.
        """
        headers = headers or {}
        try:
            validate_path(path)
            segments = _path_segments(urlparse(path).path)
            if method != "POST" or segments != ["api", "v1", "interactions"]:
                return None
            if self._interaction_service is None or self._interaction_auth is None:
                return self._json(
                    404, errors.error_response(errors.route_not_found())
                )
            self._interaction_auth.authorize(_header(headers, "authorization"))
        except errors.ApiError as error:
            return self._json(error.status, errors.error_response(error))
        except Exception:
            error = errors.runtime_unavailable()
            return self._json(error.status, errors.error_response(error))
        return None

    def handle_request(self, method, path, headers=None, body=b""):
        """Return a safe JSON API response for an HTTP request."""
        headers = headers or {}
        try:
            validate_path(path)
            parsed_path = urlparse(path).path
            segments = _path_segments(parsed_path)
            if method == "GET":
                return self._handle_get(segments)
            if method == "POST":
                return self._handle_post(segments, headers, body)
            raise errors.method_not_allowed()
        except errors.ApiError as error:
            return self._json(error.status, errors.error_response(error))
        except KeyError:
            return self._json(404, errors.error_response(errors.route_not_found()))
        except Exception:
            error = errors.runtime_unavailable()
            return self._json(error.status, errors.error_response(error))

    def _handle_get(self, segments):
        if segments == ["api", "v1", "health"]:
            return self._json(200, self._projections.health().to_dict())
        if segments == ["api", "v1", "devices"]:
            return self._json(
                200,
                {
                    "devices": [
                        device.to_dict() for device in self._projections.device_list()
                    ]
                },
            )
        if len(segments) >= 4 and segments[:3] == ["api", "v1", "devices"]:
            device_id = segments[3]
            validate_device_id(device_id)
            if len(segments) == 4:
                return self._json(200, self._projections.device_detail(device_id).to_dict())
            if len(segments) == 5 and segments[4] == "capabilities":
                return self._json(
                    200,
                    {
                        "device_id": device_id,
                        "capabilities": [
                            capability.to_dict()
                            for capability in self._projections.capabilities(device_id)
                        ],
                    },
                )
            if len(segments) == 5 and segments[4] == "state":
                state = self._projections.device_state(device_id).to_dict()
                return self._json(200, {"device_id": device_id, **state})
        raise errors.route_not_found()

    def _handle_post(self, segments, headers, body):
        if segments == ["api", "v1", "interactions"]:
            return self._handle_interaction(headers, body)
        if segments != ["api", "v1", "commands"]:
            raise errors.route_not_found()
        if self._interaction_only:
            raise errors.route_not_found()
        validate_content_type(_header(headers, "content-type"))
        if len(body) > MAX_REQUEST_BYTES:
            raise errors.payload_too_large()
        payload = parse_json_body(body)
        command_text = validate_command_payload(payload)
        with self._command_lock:
            result = self._runtime.handle_adapter_input(command_text, source=API_SOURCE)
        return self._json(
            200 if result.success else 400,
            {
                "success": bool(result.success),
                "message": result.message,
                "error": result.error,
            },
        )

    def _handle_interaction(self, headers, body):
        if self._interaction_service is None or self._interaction_auth is None:
            raise errors.route_not_found()
        self._interaction_auth.authorize(_header(headers, "authorization"))
        validate_content_type(_header(headers, "content-type"))
        if len(body) > MAX_REQUEST_BYTES:
            raise errors.payload_too_large()
        payload = parse_json_body(body)
        message = validate_interaction_payload(payload)
        response = self._interaction_service.handle(message)
        return self._json(response.status, response.body)

    def _json(self, status, body):
        try:
            json.dumps(body)
        except (TypeError, ValueError):
            error = errors.serialization_failed()
            status = error.status
            body = errors.error_response(error)
        return ApiResponse(
            status=status,
            body=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
            },
        )

    def shutdown(self):
        shutdown = getattr(self._runtime, "shutdown", None)
        if callable(shutdown):
            shutdown()


def _path_segments(path):
    return [unquote(segment) for segment in path.strip("/").split("/") if segment]


def _header(headers, name):
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None
