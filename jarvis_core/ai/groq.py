"""Optional Groq strict Structured Output provider for the AI Adapter."""

from dataclasses import dataclass
import json
import platform
import ssl
import socket
import urllib.error
import urllib.request

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
    PLAN_SCHEMA_VERSION,
    REFUSAL_REASON_CODES,
)
from jarvis_core.ai.provider import AIProviderError


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
SUPPORTED_GROQ_MODELS = {"openai/gpt-oss-20b"}
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAXIMUM_REQUEST_BYTES = 65536
DEFAULT_MAXIMUM_RESPONSE_BYTES = 262144
DEFAULT_MAXIMUM_OUTPUT_TOKENS = 256
MAX_TIMEOUT_SECONDS = 120
MAXIMUM_LIMIT_BYTES = 1024 * 1024
MAX_OUTPUT_TOKENS = 1024


@dataclass(frozen=True)
class GroqProviderConfig:
    """Immutable adapter-layer Groq provider configuration."""

    model: str = DEFAULT_GROQ_MODEL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    maximum_request_bytes: int = DEFAULT_MAXIMUM_REQUEST_BYTES
    maximum_response_bytes: int = DEFAULT_MAXIMUM_RESPONSE_BYTES
    maximum_output_tokens: int = DEFAULT_MAXIMUM_OUTPUT_TOKENS

    def __post_init__(self):
        if self.model not in SUPPORTED_GROQ_MODELS:
            raise ValueError("Groq model is not approved for Phase 10.7")
        _validate_positive_bounded_int(
            self.timeout_seconds,
            "timeout_seconds",
            MAX_TIMEOUT_SECONDS,
        )
        _validate_positive_bounded_int(
            self.maximum_request_bytes,
            "maximum_request_bytes",
            MAXIMUM_LIMIT_BYTES,
        )
        _validate_positive_bounded_int(
            self.maximum_response_bytes,
            "maximum_response_bytes",
            MAXIMUM_LIMIT_BYTES,
        )
        _validate_positive_bounded_int(
            self.maximum_output_tokens,
            "maximum_output_tokens",
            MAX_OUTPUT_TOKENS,
        )


class GroqAIProvider:
    """Groq provider that returns raw AIActionPlan data for JarvisOS validation."""

    def __init__(self, config=None, api_key=None, transport=None):
        self.config = config or GroqProviderConfig()
        self._api_key = _validate_api_key(api_key)
        self.transport = transport or GroqHttpJsonTransport()

    def generate_plan(self, context):
        request = build_groq_request(context, self.config)
        request_bytes = _json_bytes(request)
        if len(request_bytes) > self.config.maximum_request_bytes:
            raise AIProviderError(AI_RESPONSE_TOO_LARGE)
        envelope = self.transport.post_json(
            request,
            self._api_key,
            timeout_seconds=self.config.timeout_seconds,
            maximum_response_bytes=self.config.maximum_response_bytes,
        )
        return decode_groq_response(envelope)

    def generate(self, user_request, safe_context):
        """Compatibility method for the current FakeAIAdapter provider call shape."""
        return self.generate_plan(safe_context)


class GroqHttpJsonTransport:
    """Synchronous standard-library HTTPS transport for Groq."""

    def __init__(self, ssl_context=None):
        self.ssl_context = ssl_context or create_provider_ssl_context()

    def post_json(
        self,
        payload,
        api_key,
        timeout_seconds,
        maximum_response_bytes,
    ):
        request = urllib.request.Request(
            GROQ_API_URL,
            data=_json_bytes(payload),
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.ssl_context),
            _NoRedirectHandler(),
        )
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                if response.status != 200:
                    raise AIProviderError(_status_to_error(response.status))
                raw = _read_limited(response, maximum_response_bytes)
        except AIProviderError:
            raise
        except urllib.error.HTTPError as error:
            raise AIProviderError(_status_to_error(error.code)) from error
        except (socket.timeout, TimeoutError) as error:
            raise AIProviderError(AI_PROVIDER_TIMEOUT) from error
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", None)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise AIProviderError(AI_PROVIDER_TIMEOUT) from error
            raise AIProviderError(AI_PROVIDER_UNAVAILABLE) from error
        except OSError as error:
            raise AIProviderError(AI_PROVIDER_UNAVAILABLE) from error
        return _decode_json_bytes(raw)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AIProviderError(AI_PROVIDER_PROTOCOL_ERROR)


def create_provider_ssl_context():
    """Create a secure provider TLS context without global SSL monkey-patching."""
    if platform.system() == "Windows":
        try:
            import truststore
        except ImportError as error:
            raise AIProviderError(AI_PROVIDER_UNAVAILABLE) from error
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return ssl.create_default_context()


def build_groq_request(context, config):
    """Build a compact strict Structured Outputs request without logging content."""
    return {
        "model": config.model,
        "messages": (
            {
                "role": "system",
                "content": _system_instruction(),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "user_request": context.user_request,
                        "safe_context": _safe_context_payload(context),
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            },
        ),
        "temperature": 0,
        "stream": False,
        "max_completion_tokens": config.maximum_output_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "jarvis_ai_action_plan",
                "strict": True,
                "schema": groq_ai_action_plan_schema(),
            },
        },
    }


def decode_groq_response(envelope):
    if not isinstance(envelope, dict):
        raise AIProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    try:
        choices = envelope["choices"]
        message = choices[0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise AIProviderError(AI_RESPONSE_INVALID) from error
    if not isinstance(content, str) or not content.strip():
        raise AIProviderError(AI_RESPONSE_INVALID)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise AIProviderError(AI_RESPONSE_INVALID) from error
    if not isinstance(payload, dict):
        raise AIProviderError(AI_RESPONSE_INVALID)
    return payload


def groq_ai_action_plan_schema():
    string_512 = {"type": "string", "minLength": 1, "maxLength": MAX_SAFE_TEXT_LENGTH}
    optional_text = _nullable(string_512)
    policy_flags = {
        "type": "array",
        "items": {"type": "string", "minLength": 1, "maxLength": 64},
        "maxItems": 8,
    }
    step_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "index",
            "canonical_command_text",
            "safe_description",
            "target_device_id",
            "capability_name",
            "action_kind",
            "requires_confirmation",
            "policy_flags",
        ],
        "properties": {
            "index": {"type": "integer", "minimum": 0, "maximum": MAX_PLAN_STEPS - 1},
            "canonical_command_text": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_COMMAND_LENGTH,
            },
            "safe_description": string_512,
            "target_device_id": optional_text,
            "capability_name": optional_text,
            "action_kind": {
                "type": "string",
                "enum": [ACTION_KIND_READ, ACTION_KIND_MUTATE, ACTION_KIND_UNKNOWN],
            },
            "requires_confirmation": {"type": "boolean"},
            "policy_flags": policy_flags,
        },
    }
    clarification_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["question", "reason_code", "missing_fields", "candidate_options"],
        "properties": {
            "question": string_512,
            "reason_code": {
                "type": "string",
                "enum": sorted(CLARIFICATION_REASON_CODES),
            },
            "missing_fields": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 64},
                "maxItems": 8,
            },
            "candidate_options": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 128},
                "maxItems": MAX_CLARIFICATION_OPTIONS,
            },
        },
    }
    refusal_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["safe_message", "reason_code"],
        "properties": {
            "safe_message": string_512,
            "reason_code": {
                "type": "string",
                "enum": sorted(REFUSAL_REASON_CODES),
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "kind",
            "steps",
            "safe_summary",
            "clarification",
            "refusal",
            "confirmation_required",
            "policy_flags",
        ],
        "properties": {
            "schema_version": {"type": "integer", "const": PLAN_SCHEMA_VERSION},
            "kind": {
                "type": "string",
                "enum": [PLAN_KIND_EXECUTE, PLAN_KIND_CLARIFY, PLAN_KIND_REFUSE],
            },
            "steps": {
                "type": "array",
                "items": step_schema,
                "maxItems": MAX_PLAN_STEPS,
            },
            "safe_summary": string_512,
            "clarification": _nullable(clarification_schema),
            "refusal": _nullable(refusal_schema),
            "confirmation_required": {"type": "boolean"},
            "policy_flags": policy_flags,
        },
    }


def _system_instruction():
    return (
        "Return only one JSON object matching the supplied schema. "
        "Use schema_version 1 and kind execute, clarify, or refuse. "
        "Canonical commands must stay in technical English JarvisOS syntax. "
        "Spanish safe_summary, clarification questions, and refusal messages are allowed. "
        "Use one command per step, no Markdown, no reasoning, no extra fields. "
        "JarvisOS will reject unsafe, unknown, or malformed commands."
    )


def _safe_context_payload(context):
    return {
        "schema_version": context.schema_version,
        "devices": [_device_payload(device) for device in context.devices],
        "command_grammar": [_tuple_pairs_to_dict(item) for item in context.command_grammar],
        "policies": {
            "max_plan_steps": context.policies.max_plan_steps,
            "confirmation_required_for_mutations": (
                context.policies.confirmation_required_for_mutations
            ),
        },
    }


def _device_payload(device):
    return {
        "device_id": device.device_id,
        "display_name": device.display_name,
        "device_type": device.device_type,
        "capabilities": [_capability_payload(item) for item in device.capabilities],
        "state": {
            "status": device.state.status,
            "semantic_properties": dict(device.state.semantic_properties),
            "updated_at": device.state.updated_at,
        },
    }


def _capability_payload(capability):
    return {
        "name": capability.name,
        "kind": capability.kind,
        "parameters": [dict(item) for item in capability.parameters],
    }


def _tuple_pairs_to_dict(value):
    return {key: item for key, item in value}


def _nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def _json_bytes(payload):
    try:
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode(
            "utf-8",
        )
    except (TypeError, ValueError) as error:
        raise AIProviderError(AI_PROVIDER_PROTOCOL_ERROR) from error


def _read_limited(response, limit):
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise AIProviderError(AI_RESPONSE_TOO_LARGE)
    return raw


def _decode_json_bytes(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise AIProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AIProviderError(AI_RESPONSE_INVALID) from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise AIProviderError(AI_RESPONSE_INVALID) from error


def _status_to_error(status):
    if status in {401, 403}:
        return AI_PROVIDER_UNAUTHORIZED
    if status == 404:
        return AI_MODEL_NOT_FOUND
    if status == 408:
        return AI_PROVIDER_TIMEOUT
    if status == 429:
        return AI_PROVIDER_RATE_LIMITED
    if status in {500, 502, 503, 504}:
        return AI_MODEL_UNAVAILABLE
    return AI_PROVIDER_PROTOCOL_ERROR


def _validate_api_key(api_key):
    if not isinstance(api_key, str) or not api_key.strip():
        raise AIProviderError(AI_PROVIDER_UNAUTHORIZED)
    if any(ch < " " for ch in api_key):
        raise AIProviderError(AI_PROVIDER_UNAUTHORIZED)
    return api_key.strip()


def _validate_positive_bounded_int(value, label, maximum):
    if not isinstance(value, int) or value <= 0 or value > maximum:
        raise ValueError(f"{label} is invalid")
