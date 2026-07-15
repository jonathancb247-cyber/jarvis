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
MAX_OLLAMA_TIMEOUT_SECONDS = 120
MAX_OLLAMA_RESPONSE_BYTES = 1048576
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

    def __post_init__(self):
        object.__setattr__(self, "model", _validate_model(self.model))
        object.__setattr__(self, "base_url", _normalize_localhost_base_url(self.base_url))
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

    def __init__(self, config, transport=None):
        if not isinstance(config, OllamaProviderConfig):
            raise TypeError("OllamaAIProvider requires OllamaProviderConfig")
        self.config = config
        self.transport = transport or OllamaHttpJsonTransport()

    def generate_plan(self, context):
        request = build_ollama_request(self.config, context)
        envelope = self.transport.post_json(
            self.config.base_url,
            OLLAMA_GENERATE_PATH,
            request,
            self.config.timeout_seconds,
            self.config.maximum_response_bytes,
        )
        return decode_ollama_envelope(envelope, self.config.maximum_response_bytes)


def build_ollama_request(config, context):
    """Build a bounded non-streaming Ollama generate request."""
    prompt = _build_prompt(context)
    return {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
    }


def decode_ollama_envelope(envelope, maximum_response_bytes=DEFAULT_MAXIMUM_RESPONSE_BYTES):
    if not isinstance(envelope, dict):
        raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)
    if "error" in envelope:
        _raise_ollama_error(envelope.get("error"))
    response = envelope.get("response")
    if response is None and isinstance(envelope.get("message"), dict):
        response = envelope["message"].get("content")
    if not isinstance(response, str) or not response.strip():
        raise OllamaProviderError(AI_RESPONSE_INVALID)
    if len(response.encode("utf-8")) > maximum_response_bytes:
        raise OllamaProviderError(AI_RESPONSE_TOO_LARGE)
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        raise OllamaProviderError(AI_RESPONSE_INVALID)
    if not isinstance(payload, dict):
        raise OllamaProviderError(AI_RESPONSE_INVALID)
    return payload


def _build_prompt(context):
    context_payload = _safe_context_payload(context)
    examples = [
        {
            "user_request": "Enciende la lampara.",
            "plan": {
                "schema_version": 1,
                "kind": "execute",
                "steps": [
                    {
                        "index": 0,
                        "canonical_command_text": "device apply lamp_1 power.switch state=true",
                        "safe_description": "Turn lamp on.",
                        "target_device_id": "lamp_1",
                        "capability_name": "power.switch",
                        "action_kind": "mutate",
                        "requires_confirmation": False,
                        "policy_flags": [],
                    }
                ],
                "safe_summary": "Turn lamp on.",
                "clarification": None,
                "refusal": None,
                "confirmation_required": False,
                "policy_flags": [],
            },
        },
        {
            "user_request": "Lee el estado de la lampara.",
            "plan": {
                "schema_version": 1,
                "kind": "execute",
                "steps": [
                    {
                        "index": 0,
                        "canonical_command_text": "device read lamp_1 status.read",
                        "safe_description": "Read lamp status.",
                        "target_device_id": "lamp_1",
                        "capability_name": "status.read",
                        "action_kind": "read",
                        "requires_confirmation": False,
                        "policy_flags": [],
                    }
                ],
                "safe_summary": "Read lamp status.",
                "clarification": None,
                "refusal": None,
                "confirmation_required": False,
                "policy_flags": [],
            },
        },
        {
            "user_request": "No se que lampara usar.",
            "plan": {
                "schema_version": 1,
                "kind": "clarify",
                "steps": [],
                "safe_summary": "Need a target device.",
                "clarification": {
                    "question": "Which device should I use?",
                    "reason_code": "ambiguous_device",
                    "missing_fields": ["device_id"],
                    "candidate_options": ["lamp_1"],
                },
                "refusal": None,
                "confirmation_required": False,
                "policy_flags": [],
            },
        },
    ]
    payload = {
        "instructions": [
            "Return JSON only.",
            "Return an AIActionPlan schema_version 1.",
            "Allowed kind values are execute, clarify, refuse.",
            "Canonical JarvisOS command text must stay in technical English.",
            "Do not include URLs, IP addresses, bindings, credentials, diagnostics, or runtime internals.",
            "Do not create more than five steps.",
        ],
        "schema": {
            "schema_version": PLAN_SCHEMA_VERSION,
            "kinds": ["execute", "clarify", "refuse"],
            "max_steps": MAX_PLAN_STEPS,
            "max_command_length": MAX_COMMAND_LENGTH,
        },
        "safe_context": context_payload,
        "examples": examples,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


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

