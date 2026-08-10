"""Optional Gemini structured-output provider for the AI Adapter boundary."""

import http.client
import json
import os
import socket
import ssl
from dataclasses import dataclass

from jarvis_core.ai.transport_security import create_provider_ssl_context
from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
    ACTION_KIND_READ,
    ACTION_KIND_UNKNOWN,
    AI_MODEL_NOT_FOUND,
    AI_MODEL_UNAVAILABLE,
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_RATE_LIMITED,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAUTHORIZED,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
    CLARIFICATION_REASON_CODES,
    MAX_CLARIFICATION_OPTIONS,
    MAX_COMMAND_LENGTH,
    MAX_PLAN_STEPS,
    MAX_SAFE_TEXT_LENGTH,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
    REFUSAL_REASON_CODES,
)
from jarvis_core.ai.validation import AIValidationError


GEMINI_API_HOST = "generativelanguage.googleapis.com"
GEMINI_INTERACTIONS_PATH = "/v1/interactions"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
SUPPORTED_GEMINI_MODELS = {
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
}
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAXIMUM_REQUEST_BYTES = 24 * 1024
DEFAULT_MAXIMUM_RESPONSE_BYTES = 64 * 1024
DEFAULT_MAXIMUM_OUTPUT_TOKENS = 512
MINIMUM_LIMIT_BYTES = 1024


class GeminiProviderError(AIValidationError):
    """Safe Gemini provider error."""


@dataclass(frozen=True)
class GeminiProviderConfig:
    """Immutable adapter-layer configuration for Gemini."""

    model: str = DEFAULT_GEMINI_MODEL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    maximum_request_bytes: int = DEFAULT_MAXIMUM_REQUEST_BYTES
    maximum_response_bytes: int = DEFAULT_MAXIMUM_RESPONSE_BYTES
    maximum_output_tokens: int = DEFAULT_MAXIMUM_OUTPUT_TOKENS

    def __post_init__(self):
        if self.model not in SUPPORTED_GEMINI_MODELS:
            raise ValueError("Gemini model is not approved for this phase")
        _require_positive_int(self.timeout_seconds, "timeout_seconds", maximum=120)
        _require_positive_int(
            self.maximum_request_bytes,
            "maximum_request_bytes",
            minimum=MINIMUM_LIMIT_BYTES,
            maximum=256 * 1024,
        )
        _require_positive_int(
            self.maximum_response_bytes,
            "maximum_response_bytes",
            minimum=MINIMUM_LIMIT_BYTES,
            maximum=512 * 1024,
        )
        _require_positive_int(
            self.maximum_output_tokens,
            "maximum_output_tokens",
            minimum=1,
            maximum=2048,
        )


@dataclass(frozen=True)
class GeminiHttpResponse:
    status_code: int
    body: object
    headers: tuple = ()


class GeminiHttpsTransport:
    """Synchronous HTTPS JSON transport for the fixed Gemini Interactions API."""

    def __init__(self, ssl_context=None):
        self.ssl_context = ssl_context or create_provider_ssl_context()

    def post_json(self, path, payload, headers, timeout_seconds, max_response_bytes):
        if path != GEMINI_INTERACTIONS_PATH:
            raise GeminiProviderError(AI_PROVIDER_PROTOCOL_ERROR)
        if not isinstance(headers, dict):
            raise GeminiProviderError(AI_PROVIDER_PROTOCOL_ERROR)
        try:
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        except (TypeError, ValueError) as error:
            raise GeminiProviderError(AI_PROVIDER_PROTOCOL_ERROR) from error
        connection = http.client.HTTPSConnection(
            GEMINI_API_HOST,
            timeout=timeout_seconds,
            context=self.ssl_context,
        )
        try:
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(max_response_bytes + 1)
        except TimeoutError as error:
            raise GeminiProviderError(AI_PROVIDER_TIMEOUT) from error
        except (OSError, http.client.HTTPException, ssl.SSLError, socket.timeout) as error:
            raise GeminiProviderError(AI_PROVIDER_UNAVAILABLE) from error
        finally:
            connection.close()
        if len(raw) > max_response_bytes:
            raise GeminiProviderError(AI_RESPONSE_TOO_LARGE)
        try:
            text = raw.decode("utf-8")
            body = json.loads(text) if text else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GeminiProviderError(AI_RESPONSE_INVALID) from error
        return GeminiHttpResponse(
            status_code=response.status,
            body=body,
            headers=tuple((key.lower(), value) for key, value in response.getheaders()),
        )


class GeminiAIProvider:
    """Gemini provider that returns untrusted raw AIActionPlan-shaped data."""

    def __init__(self, api_key, config=None, transport=None):
        self.api_key = _validate_api_key(api_key)
        self.config = config or GeminiProviderConfig()
        self.transport = transport or GeminiHttpsTransport()

    @classmethod
    def from_environment(cls, config=None, transport=None, environ=None):
        environ = environ or os.environ
        return cls(environ.get(GEMINI_API_KEY_ENV), config=config, transport=transport)

    def generate_plan(self, context):
        request = self.build_request(context)
        request_bytes = len(
            json.dumps(request, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        if request_bytes > self.config.maximum_request_bytes:
            raise GeminiProviderError(AI_PROVIDER_PROTOCOL_ERROR)
        response = self.transport.post_json(
            GEMINI_INTERACTIONS_PATH,
            request,
            self._headers(),
            self.config.timeout_seconds,
            self.config.maximum_response_bytes,
        )
        self._raise_for_status(response)
        return self._extract_structured_plan(response.body)

    def build_request(self, context):
        return {
            "model": self.config.model,
            "input": _build_input(context),
            "system_instruction": _system_instruction(),
            "stream": False,
            "store": False,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": ai_action_plan_schema(),
            },
            "generation_config": {
                "max_output_tokens": self.config.maximum_output_tokens,
                "thinking_level": "minimal",
                "thinking_summaries": "none",
            },
        }

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

    def _raise_for_status(self, response):
        status = response.status_code
        if 200 <= status < 300:
            return
        if status in {401, 403}:
            raise GeminiProviderError(AI_PROVIDER_UNAUTHORIZED)
        if status == 404:
            raise GeminiProviderError(AI_MODEL_NOT_FOUND)
        if status == 408:
            raise GeminiProviderError(AI_PROVIDER_TIMEOUT)
        if status == 413:
            raise GeminiProviderError(AI_RESPONSE_TOO_LARGE)
        if status == 429:
            raise GeminiProviderError(AI_PROVIDER_RATE_LIMITED)
        if status in {500, 502, 503, 504}:
            raise GeminiProviderError(AI_MODEL_UNAVAILABLE)
        raise GeminiProviderError(AI_PROVIDER_PROTOCOL_ERROR)

    def _extract_structured_plan(self, body):
        if not isinstance(body, dict):
            raise GeminiProviderError(AI_RESPONSE_INVALID)
        if body.get("status") not in (None, "completed"):
            raise GeminiProviderError(AI_RESPONSE_INVALID)
        text = body.get("output_text")
        if not isinstance(text, str):
            text = _find_model_text(body.get("steps", []))
        if not isinstance(text, str) or not text.strip():
            raise GeminiProviderError(AI_RESPONSE_INVALID)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise GeminiProviderError(AI_RESPONSE_INVALID) from error
        if not isinstance(payload, dict):
            raise GeminiProviderError(AI_RESPONSE_INVALID)
        return payload


def ai_action_plan_schema():
    return _closed_object(
        {
            "schema_version": {"type": "integer", "enum": [1]},
            "kind": {"type": "string", "enum": sorted(_plan_kinds())},
            "steps": {
                "type": "array",
                "items": ai_action_step_schema(),
                "minItems": 0,
                "maxItems": MAX_PLAN_STEPS,
            },
            "safe_summary": {
                "type": "string",
                "description": f"Spanish safe summary, maximum {MAX_SAFE_TEXT_LENGTH} characters.",
            },
            "clarification": _nullable_object(ai_clarification_schema()),
            "refusal": _nullable_object(ai_refusal_schema()),
            "confirmation_required": {"type": "boolean"},
            "policy_flags": _string_enum_array(
                [
                    "requires_confirmation",
                    "multi_step",
                    "read_only",
                    "device_mutation",
                    "safety_refusal",
                ],
                max_items=MAX_PLAN_STEPS,
            ),
        },
        [
            "schema_version",
            "kind",
            "steps",
            "safe_summary",
            "clarification",
            "refusal",
            "confirmation_required",
            "policy_flags",
        ],
    )


def ai_action_step_schema():
    return _closed_object(
        {
            "index": {"type": "integer", "minimum": 0, "maximum": MAX_PLAN_STEPS - 1},
            "canonical_command_text": {
                "type": "string",
                "description": f"Exact English JarvisOS command, maximum {MAX_COMMAND_LENGTH} characters.",
            },
            "safe_description": {
                "type": "string",
                "description": f"Spanish or technical safe step description, maximum {MAX_SAFE_TEXT_LENGTH} characters.",
            },
            "target_device_id": {"type": ["string", "null"]},
            "capability_name": {"type": ["string", "null"]},
            "action_kind": {
                "type": "string",
                "enum": [ACTION_KIND_MUTATE, ACTION_KIND_READ, ACTION_KIND_UNKNOWN],
            },
            "requires_confirmation": {"type": "boolean"},
            "policy_flags": _string_enum_array(
                [
                    "read_only",
                    "device_mutation",
                    "requires_confirmation",
                    "unknown_action",
                ],
                max_items=MAX_PLAN_STEPS,
            ),
        },
        [
            "index",
            "canonical_command_text",
            "safe_description",
            "target_device_id",
            "capability_name",
            "action_kind",
            "requires_confirmation",
            "policy_flags",
        ],
    )


def ai_clarification_schema():
    return _closed_object(
        {
            "question": {
                "type": "string",
                "description": f"Spanish clarification question, maximum {MAX_SAFE_TEXT_LENGTH} characters.",
            },
            "reason_code": {
                "type": "string",
                "enum": sorted(CLARIFICATION_REASON_CODES),
            },
            "missing_fields": _string_array(max_items=MAX_CLARIFICATION_OPTIONS),
            "candidate_options": _string_array(max_items=MAX_CLARIFICATION_OPTIONS),
        },
        ["question", "reason_code", "missing_fields", "candidate_options"],
    )


def ai_refusal_schema():
    return _closed_object(
        {
            "safe_message": {
                "type": "string",
                "description": f"Spanish refusal message, maximum {MAX_SAFE_TEXT_LENGTH} characters.",
            },
            "reason_code": {"type": "string", "enum": sorted(REFUSAL_REASON_CODES)},
        },
        ["safe_message", "reason_code"],
    )


def _closed_object(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _nullable_object(schema):
    nullable = dict(schema)
    nullable["type"] = ["object", "null"]
    return nullable


def _string_array(max_items):
    return {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 0,
        "maxItems": max_items,
    }


def _string_enum_array(values, max_items):
    schema = _string_array(max_items)
    schema["items"] = {"type": "string", "enum": values}
    return schema


def _plan_kinds():
    return {PLAN_KIND_EXECUTE, PLAN_KIND_CLARIFY, PLAN_KIND_REFUSE}


def _system_instruction():
    return (
        "You are JarvisOS planning middleware. Return only JSON matching the "
        "provided schema. User-facing summaries, questions, and refusals may be "
        "Spanish. canonical_command_text must remain exact technical English "
        "JarvisOS grammar. Do not invent devices or capabilities. Do not include "
        "chain-of-thought."
    )


def _build_input(context):
    return json.dumps(
        {
            "user_request": context.user_request,
            "safe_context": _safe_context_payload(context),
            "canonical_command_grammar": [
                "device read <device_id> <capability_name>",
                "device apply <device_id> <capability_name> <name=value>",
                "device state <device_id>",
                "device list",
            ],
            "plan_limits": {
                "max_steps": MAX_PLAN_STEPS,
                "mutations_require_confirmation": True,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _safe_context_payload(context):
    return {
        "schema_version": context.schema_version,
        "session_context": list(context.session_context),
        "devices": [_device_payload(device) for device in context.devices],
        "command_grammar": [dict(item) for item in context.command_grammar],
        "policies": {
            "max_plan_steps": context.policies.max_plan_steps,
            "confirmation_required_for_mutations": (
                context.policies.confirmation_required_for_mutations
            ),
        },
        "previous_results": [tuple(result) for result in context.previous_results],
    }


def _device_payload(device):
    return {
        "device_id": device.device_id,
        "display_name": device.display_name,
        "device_type": device.device_type,
        "capabilities": [
            {
                "name": capability.name,
                "kind": capability.kind,
                "parameters": [dict(parameter) for parameter in capability.parameters],
            }
            for capability in device.capabilities
        ],
        "state": {
            "status": device.state.status,
            "semantic_properties": list(device.state.semantic_properties),
            "updated_at": device.state.updated_at,
        },
    }


def _find_model_text(steps):
    if not isinstance(steps, list):
        raise GeminiProviderError(AI_RESPONSE_INVALID)
    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for item in step.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                return item.get("text")
    raise GeminiProviderError(AI_RESPONSE_INVALID)


def _validate_api_key(api_key):
    if not isinstance(api_key, str) or not api_key.strip():
        raise GeminiProviderError(AI_PROVIDER_UNAUTHORIZED)
    key = api_key.strip()
    if any(ch.isspace() for ch in key):
        raise GeminiProviderError(AI_PROVIDER_UNAUTHORIZED)
    return key


def _require_positive_int(value, label, minimum=1, maximum=None):
    if not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} is invalid")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} is invalid")
