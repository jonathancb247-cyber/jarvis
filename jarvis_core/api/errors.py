"""Safe Runtime API error contracts."""

from dataclasses import dataclass


API_REQUEST_INVALID = "api_request_invalid"
API_ROUTE_NOT_FOUND = "api_route_not_found"
API_METHOD_NOT_ALLOWED = "api_method_not_allowed"
API_PAYLOAD_TOO_LARGE = "api_payload_too_large"
API_COMMAND_INVALID = "api_command_invalid"
API_RUNTIME_UNAVAILABLE = "api_runtime_unavailable"
API_RESPONSE_SERIALIZATION_FAILED = "api_response_serialization_failed"
API_UNSUPPORTED_MEDIA_TYPE = "api_request_invalid"
API_UNAUTHORIZED = "api_unauthorized"
API_INTERACTION_BUSY = "api_interaction_busy"
API_INTERACTION_PROVIDER_UNAVAILABLE = "api_interaction_provider_unavailable"
API_INTERACTION_PROVIDER_TIMEOUT = "api_interaction_provider_timeout"
API_INTERACTION_PROVIDER_INVALID = "api_interaction_provider_invalid"


@dataclass(frozen=True)
class ApiError(Exception):
    """Adapter-local API error that never carries internal exception details."""

    code: str
    message: str
    status: int


def error_response(error):
    return {
        "success": False,
        "message": error.message,
        "error": error.code,
    }


def request_invalid(message="API request is invalid."):
    return ApiError(API_REQUEST_INVALID, message, 400)


def route_not_found():
    return ApiError(API_ROUTE_NOT_FOUND, "API route was not found.", 404)


def method_not_allowed():
    return ApiError(API_METHOD_NOT_ALLOWED, "API method is not allowed.", 405)


def payload_too_large():
    return ApiError(API_PAYLOAD_TOO_LARGE, "API payload is too large.", 413)


def unsupported_media_type():
    return ApiError(API_UNSUPPORTED_MEDIA_TYPE, "Content type must be application/json.", 415)


def command_invalid(message="API command is invalid."):
    return ApiError(API_COMMAND_INVALID, message, 400)


def runtime_unavailable():
    return ApiError(API_RUNTIME_UNAVAILABLE, "Runtime is unavailable.", 500)


def unauthorized():
    return ApiError(API_UNAUTHORIZED, "API authentication is required.", 401)


def interaction_busy():
    return ApiError(
        API_INTERACTION_BUSY,
        "Interaction capacity is temporarily unavailable.",
        503,
    )


def interaction_provider_unavailable():
    return ApiError(
        API_INTERACTION_PROVIDER_UNAVAILABLE,
        "Local understanding provider is unavailable.",
        503,
    )


def interaction_provider_timeout():
    return ApiError(
        API_INTERACTION_PROVIDER_TIMEOUT,
        "Local understanding provider timed out.",
        504,
    )


def interaction_provider_invalid():
    return ApiError(
        API_INTERACTION_PROVIDER_INVALID,
        "Local understanding response was invalid.",
        502,
    )


def serialization_failed():
    return ApiError(
        API_RESPONSE_SERIALIZATION_FAILED,
        "API response could not be serialized.",
        500,
    )
