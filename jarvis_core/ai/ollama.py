"""Optional localhost Ollama provider for the experimental AI Adapter."""

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from jarvis_core.ai.contracts import (
    AI_MODEL_NOT_FOUND,
    AI_MODEL_UNAVAILABLE,
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
    MAX_COMMAND_LENGTH,
    MAX_CONTEXT_DEVICES,
    MAX_PLAN_STEPS,
    MAX_SAFE_TEXT_LENGTH,
    PLAN_SCHEMA_VERSION,
)


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 30
DEFAULT_MAXIMUM_RESPONSE_BYTES = 262144
DEFAULT_OLLAMA_KEEP_ALIVE = "10m"
DEFAULT_OLLAMA_NUM_PREDICT = 192
MAX_OLLAMA_TIMEOUT_SECONDS = 120
MAX_OLLAMA_RESPONSE_BYTES = 1048576
MAX_OLLAMA_NUM_PREDICT = 512
OLLAMA_GENERATE_PATH = "/api/generate"


class OllamaProviderError(Exception):
    """Safe provider error normalized before reaching adapter results."""

    def __init__(self, code):
        super().__init__("AI provider request failed")
        self.code = code


@dataclass(frozen=True)
class OllamaProviderConfig:
    """Immutable adapter-layer configuration for localhost Ollama."""

    model: str
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    timeout_seconds: int = DEFAULT_OLLAMA_TIMEOUT_SECONDS
    maximum_response_bytes: int = DEFAULT_MAXIMUM_RESPONSE_BYTES
    keep_alive: str = DEFAULT_OLLAMA_KEEP_ALIVE
    num_predict: int = DEFAULT_OLLAMA_NUM_PREDICT

    def __post_init__(self):
        object.__setattr__(self, "model", _validate_model(self.model))
        object.__setattr__(self, "base_url", _normalize_localhost_base_url(self.base_url))
        object.__setattr__(self, "keep_alive", _validate_keep_alive(self.keep_alive))
        if (
            not isinstance(self.timeout_seconds, int)
            or self.timeout_seconds <= 0
            or self.timeout_seconds > MAX_OLLAMA_TIMEOUT_SECONDS
        ):
            raise ValueError("Ollama timeout must be a positive bounded integer")
        if (
            not isinstance(self.maximum_response_bytes, int)
            or self.maximum_response_bytes <= 0
            or self.maximum_response_bytes > MAX_OLLAMA_RESPONSE_BYTES
        ):
            raise ValueError("Ollama response size must be a positive bounded integer")
        if (
            not isinstance(self.num_predict, int)
            or self.num_predict <= 0
            or self.num_predict > MAX_OLLAMA_NUM_PREDICT
        ):
            raise ValueError("Ollama output token cap must be a positive bounded integer")


class OllamaHttpJsonTransport:
    """Synchronous stdlib JSON transport for localhost Ollama."""

    def post_json(self, base_url, path, payload, timeout_seconds, maximum_response_bytes):
        if path != OLLAMA_GENERATE_PATH:
            raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            urllib.parse.urljoin(base_url + "/", path.lstrip("/")),
            data=encoded,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        opener = urllib.request.build_opener(_NoRedirectHandler)
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                body = _read_limited(response, maximum_response_bytes)
        except urllib.error.HTTPError as error:
            _raise_http_error(error)
        except (TimeoutError, socket.timeout):
            raise OllamaProviderError(AI_PROVIDER_TIMEOUT)
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise OllamaProviderError(AI_PROVIDER_TIMEOUT)
            raise OllamaProviderError(AI_PROVIDER_UNAVAILABLE)
        except OSError:
            raise OllamaProviderError(AI_PROVIDER_UNAVAILABLE)
        return _decode_json_bytes(body)


class OllamaAIProvider:
    """Generate raw Structured Plan payloads through a local Ollama server."""

    def __init__(self, config, transport=None, diagnostic_enabled=False):
        if not isinstance(config, OllamaProviderConfig):
            raise TypeError("OllamaAIProvider requires OllamaProviderConfig")
        self.config = config
        self.transport = transport or OllamaHttpJsonTransport()
        self.diagnostic_enabled = bool(diagnostic_enabled)
        self._diagnostics = []

    def generate_plan(self, context):
        self._diagnostics = []
        request = build_ollama_request(self.config, context)
        self._record_diagnostic(
            "provider_request_built",
            request_bytes=_json_size(request),
            prompt_char_count=len(request["prompt"]),
            example_count=_example_count(request["prompt"]),
            keep_alive_present="keep_alive" in request,
            output_token_cap=request.get("options", {}).get("num_predict"),
        )
        envelope = self.transport.post_json(
            self.config.base_url,
            OLLAMA_GENERATE_PATH,
            request,
            self.config.timeout_seconds,
            self.config.maximum_response_bytes,
        )
        self._record_diagnostic(
            "provider_call_completed",
            envelope_keys=_safe_keys(envelope),
        )
        return decode_ollama_envelope(
            envelope,
            self.config.maximum_response_bytes,
            diagnostic_recorder=self._record_diagnostic,
        )

    def record_adapter_error(self, code, reason):
        self._record_diagnostic(
            "adapter_validation_failed",
            error_code=code,
            reason=reason,
        )

    def consume_diagnostics(self):
        diagnostics = tuple(self._diagnostics)
        self._diagnostics = []
        return diagnostics

    def _record_diagnostic(self, stage, **fields):
        if not self.diagnostic_enabled:
            return
        safe_fields = {"stage": stage}
        for key, value in fields.items():
            if isinstance(value, (str, int, bool)) or value is None:
                safe_fields[key] = value
            elif isinstance(value, (tuple, list)):
                safe_fields[key] = ",".join(str(item) for item in value[:16])
        self._diagnostics.append(safe_fields)


def build_ollama_request(config, context):
    """Build a bounded non-streaming Ollama generate request."""
    prompt = _build_prompt(context)
    return {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": config.keep_alive,
        "options": {
            "num_predict": config.num_predict,
            "temperature": 0,
        },
    }


def decode_ollama_envelope(
    envelope,
    maximum_response_bytes=DEFAULT_MAXIMUM_RESPONSE_BYTES,
    diagnostic_recorder=None,
):
    if not isinstance(envelope, dict):
        raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    if "error" in envelope:
        _raise_ollama_error(envelope.get("error"))
    response = envelope.get("response")
    if response is None and isinstance(envelope.get("message"), dict):
        response = envelope["message"].get("content")
    if not isinstance(response, str) or not response.strip():
        raise OllamaProviderError(AI_RESPONSE_INVALID)
    response_bytes = len(response.encode("utf-8"))
    _record_optional(
        diagnostic_recorder,
        "provider_response_received",
        response_bytes=response_bytes,
    )
    if response_bytes > maximum_response_bytes:
        raise OllamaProviderError(AI_RESPONSE_TOO_LARGE)
    content = _strip_single_json_code_fence(response)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        _record_optional(diagnostic_recorder, "provider_response_not_json")
        raise OllamaProviderError(AI_RESPONSE_INVALID)
    if not isinstance(payload, dict):
        _record_optional(
            diagnostic_recorder,
            "provider_response_json_decoded",
            top_level_type=type(payload).__name__,
        )
        raise OllamaProviderError(AI_RESPONSE_INVALID)
    _record_optional(
        diagnostic_recorder,
        "provider_response_json_decoded",
        top_level_type="dict",
        top_level_fields=_safe_keys(payload),
    )
    return _normalize_provider_payload(payload, diagnostic_recorder)


def ai_action_plan_json_schema():
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
            "index": {"type": "integer", "minimum": 0},
            "canonical_command_text": {"type": "string", "minLength": 1, "maxLength": MAX_COMMAND_LENGTH},
            "safe_description": {"type": "string", "minLength": 1, "maxLength": MAX_SAFE_TEXT_LENGTH},
            "target_device_id": {"type": ["string", "null"], "maxLength": MAX_SAFE_TEXT_LENGTH},
            "capability_name": {"type": ["string", "null"], "maxLength": MAX_SAFE_TEXT_LENGTH},
            "action_kind": {"type": "string", "enum": ["read", "mutate", "unknown"]},
            "requires_confirmation": {"type": "boolean"},
            "policy_flags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        },
    }
    clarification_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["question", "reason_code", "missing_fields", "candidate_options"],
        "properties": {
            "question": {"type": "string", "minLength": 1, "maxLength": MAX_SAFE_TEXT_LENGTH},
            "reason_code": {
                "type": "string",
                "enum": [
                    "ambiguous_device",
                    "missing_parameter",
                    "unsupported_request",
                    "multiple_possible_actions",
                    "safety_uncertainty",
                    "insufficient_context",
                ],
            },
            "missing_fields": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
            "candidate_options": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        },
    }
    refusal_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["safe_message", "reason_code"],
        "properties": {
            "safe_message": {"type": "string", "minLength": 1, "maxLength": MAX_SAFE_TEXT_LENGTH},
            "reason_code": {
                "type": "string",
                "enum": [
                    "forbidden_operation",
                    "policy_violation",
                    "unsafe_request",
                    "unsupported_operation",
                    "invalid_provider_output",
                ],
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
            "kind": {"type": "string", "enum": ["execute", "clarify", "refuse"]},
            "steps": {"type": "array", "items": step_schema, "maxItems": MAX_PLAN_STEPS},
            "safe_summary": {"type": "string", "maxLength": MAX_SAFE_TEXT_LENGTH},
            "clarification": {"anyOf": [clarification_schema, {"type": "null"}]},
            "refusal": {"anyOf": [refusal_schema, {"type": "null"}]},
            "confirmation_required": {"type": "boolean"},
            "policy_flags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        },
    }


def _build_prompt(context):
    context_payload = _safe_context_payload(context)
    examples = [
        {
            "user_request": "Lee el estado de la lampara.",
            "kind": "execute",
            "canonical_command_text": "device read lamp_1 status.read",
            "action_kind": "read",
        },
        {
            "user_request": "Enciende la lampara.",
            "kind": "execute",
            "canonical_command_text": "device apply lamp_1 power.switch state=true",
            "action_kind": "mutate",
        },
        {
            "user_request": "Borra archivos.",
            "kind": "refuse",
            "reason_code": "forbidden_operation",
        },
    ]
    payload = {
        "instructions": [
            "Return JSON only.",
            "Plan only for safe_context.user_request; examples show intent mapping only.",
            "Return the plan object at root; first key schema_version.",
            "Forbidden wrappers: AIActionPlan, actionPlan, plan, result, response, Markdown.",
            "No reasoning text.",
            "Required fields once; null for absent clarification/refusal; [] for empty lists.",
            "No unknown fields; schema_version=1; kind=execute|clarify|refuse.",
            "steps items are objects, indexed 0..n-1; one step equals one canonical command.",
            "Canonical commands stay technical English; summaries/questions use Spanish.",
            "JarvisOS validates commands and confirmation.",
            "Refuse filesystem, shell, destructive computer, credential, or unsafe requests.",
            "Exclude infrastructure, bindings, credentials, diagnostics, and internals.",
            "Max five steps.",
        ],
        "schema": {
            "schema_version": PLAN_SCHEMA_VERSION,
            "kinds": ["execute", "clarify", "refuse"],
            "max_steps": MAX_PLAN_STEPS,
            "max_command_length": MAX_COMMAND_LENGTH,
            "step_index_rule": "0..n-1",
            "step_fields": [
                "index",
                "canonical_command_text",
                "safe_description",
                "target_device_id",
                "capability_name",
                "action_kind",
                "requires_confirmation",
                "policy_flags",
            ],
        },
        "safe_context": context_payload,
        "examples": examples,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _json_size(payload):
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _example_count(prompt):
    try:
        payload = json.loads(prompt)
    except json.JSONDecodeError:
        return None
    examples = payload.get("examples")
    return len(examples) if isinstance(examples, list) else None


def _normalize_provider_payload(payload, diagnostic_recorder=None):
    if set(payload) == {"actionPlan"} and isinstance(payload["actionPlan"], dict):
        _record_optional(diagnostic_recorder, "provider_wrapper_unwrapped", wrapper="actionPlan")
        return payload["actionPlan"]
    return payload


def _strip_single_json_code_fence(response):
    stripped = response.strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return response
    lines = stripped.splitlines()
    if len(lines) < 3:
        return response
    first = lines[0].strip().lower()
    if first not in {"```", "```json"}:
        return response
    return "\n".join(lines[1:-1]).strip()


def _record_optional(recorder, stage, **fields):
    if callable(recorder):
        recorder(stage, **fields)


def _safe_keys(value):
    if not isinstance(value, dict):
        return ()
    return tuple(sorted(str(key)[:64] for key in value.keys()))


def _safe_context_payload(context):
    return {
        "schema_version": context.schema_version,
        "user_request": context.user_request,
        "session_context": _pairs_to_dict(context.session_context),
        "devices": [_device_payload(device) for device in context.devices[:MAX_CONTEXT_DEVICES]],
        "command_grammar": [_pairs_to_dict(item) for item in context.command_grammar],
        "policies": {
            "max_plan_steps": context.policies.max_plan_steps,
            "confirmation_required_for_mutations": context.policies.confirmation_required_for_mutations,
        },
        "previous_results": [
            {
                "step_index": result.step_index,
                "success": result.success,
                "message": result.message,
                "error": result.error,
            }
            for result in context.previous_results
        ],
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
                "parameters": [_pairs_to_dict(item) for item in capability.parameters],
            }
            for capability in device.capabilities
        ],
        "state": {
            "status": device.state.status,
            "semantic_properties": _pairs_to_dict(device.state.semantic_properties),
            "updated_at": device.state.updated_at,
        },
    }


def _pairs_to_dict(items):
    result = {}
    for item in items:
        if isinstance(item, tuple) and len(item) == 2:
            result[str(item[0])[:MAX_SAFE_TEXT_LENGTH]] = item[1]
    return result


def _validate_model(model):
    if not isinstance(model, str):
        raise ValueError("Ollama model must be a string")
    normalized = model.strip()
    if not normalized or len(normalized) > 128:
        raise ValueError("Ollama model is invalid")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")
    if normalized[0] in ".:-" or any(ch not in allowed for ch in normalized):
        raise ValueError("Ollama model is invalid")
    return normalized


def _validate_keep_alive(keep_alive):
    if not isinstance(keep_alive, str):
        raise ValueError("Ollama keep_alive must be a string")
    normalized = keep_alive.strip()
    if not normalized or len(normalized) > 16:
        raise ValueError("Ollama keep_alive is invalid")
    allowed = set("0123456789smh")
    if any(ch not in allowed for ch in normalized):
        raise ValueError("Ollama keep_alive is invalid")
    return normalized


def _normalize_localhost_base_url(base_url):
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("Ollama base_url is invalid")
    parsed = urllib.parse.urlparse(base_url.strip())
    if parsed.scheme != "http":
        raise ValueError("Ollama base_url must use http")
    if parsed.username or parsed.password:
        raise ValueError("Ollama base_url cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Ollama base_url cannot contain query or fragment")
    if parsed.path not in ("", "/"):
        raise ValueError("Ollama base_url cannot contain an arbitrary path")
    host = (parsed.hostname or "").lower()
    if host == "localhost":
        host = "127.0.0.1"
    if host != "127.0.0.1":
        raise ValueError("Ollama base_url must be localhost only")
    if parsed.port is None:
        netloc = host
    else:
        netloc = f"{host}:{parsed.port}"
    return urllib.parse.urlunparse(("http", netloc, "", "", "", ""))


def _read_limited(response, maximum_response_bytes):
    chunks = []
    total = 0
    while True:
        chunk = response.read(min(65536, maximum_response_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum_response_bytes:
            raise OllamaProviderError(AI_RESPONSE_TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_json_bytes(body):
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)


def _raise_http_error(error):
    if error.code == 404:
        raise OllamaProviderError(AI_MODEL_NOT_FOUND)
    if error.code in {408, 504}:
        raise OllamaProviderError(AI_PROVIDER_TIMEOUT)
    if error.code in {429, 500, 502, 503}:
        raise OllamaProviderError(AI_MODEL_UNAVAILABLE)
    if 300 <= error.code < 400:
        raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)


def _raise_ollama_error(error):
    text = str(error).lower() if error is not None else ""
    if "not found" in text or "pull" in text:
        raise OllamaProviderError(AI_MODEL_NOT_FOUND)
    if "unavailable" in text or "loading" in text:
        raise OllamaProviderError(AI_MODEL_UNAVAILABLE)
    raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)
