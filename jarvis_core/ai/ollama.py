"""Optional Ollama local structured-output provider for the AI Adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import socket

from jarvis_core.ai.contracts import (
    AI_MODEL_NOT_FOUND,
    AI_MODEL_UNAVAILABLE,
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
    MAX_COMMAND_LENGTH,
    MAX_PLAN_STEPS,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
)
from jarvis_core.ai.gemini import ai_action_plan_schema
from jarvis_core.ai.validation import AIValidationError


OLLAMA_CHAT_PATH = "/api/chat"
DEFAULT_OLLAMA_HOST = "127.0.0.1"
DEFAULT_OLLAMA_PORT = 11434
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAXIMUM_REQUEST_BYTES = 24 * 1024
DEFAULT_MAXIMUM_RESPONSE_BYTES = 64 * 1024
DEFAULT_MAXIMUM_OUTPUT_TOKENS = 512
LOCALHOSTS = {"127.0.0.1", "localhost"}


class OllamaProviderError(AIValidationError):
    """Safe Ollama provider error."""


@dataclass(frozen=True)
class OllamaProviderConfig:
    model: str
    host: str = DEFAULT_OLLAMA_HOST
    port: int = DEFAULT_OLLAMA_PORT
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    maximum_request_bytes: int = DEFAULT_MAXIMUM_REQUEST_BYTES
    maximum_response_bytes: int = DEFAULT_MAXIMUM_RESPONSE_BYTES
    maximum_output_tokens: int = DEFAULT_MAXIMUM_OUTPUT_TOKENS

    def __post_init__(self):
        _require_model(self.model)
        if self.host not in LOCALHOSTS:
            raise ValueError("Ollama host must be localhost-only")
        _require_int(self.port, "port", minimum=1, maximum=65535)
        _require_int(self.timeout_seconds, "timeout_seconds", minimum=1, maximum=180)
        _require_int(self.maximum_request_bytes, "maximum_request_bytes", minimum=1024, maximum=256 * 1024)
        _require_int(self.maximum_response_bytes, "maximum_response_bytes", minimum=1024, maximum=512 * 1024)
        _require_int(self.maximum_output_tokens, "maximum_output_tokens", minimum=1, maximum=4096)


@dataclass(frozen=True)
class OllamaHttpResponse:
    status_code: int
    body: object


class OllamaHttpTransport:
    """Synchronous localhost JSON transport for Ollama."""

    def post_json(self, host, port, path, payload, timeout_seconds, max_response_bytes):
        if host not in LOCALHOSTS or path != OLLAMA_CHAT_PATH:
            raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)
        try:
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR) from exc
        connection = http.client.HTTPConnection(host, port=port, timeout=timeout_seconds)
        try:
            connection.request("POST", path, body=body, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read(max_response_bytes + 1)
        except TimeoutError as exc:
            raise OllamaProviderError(AI_PROVIDER_TIMEOUT) from exc
        except (OSError, http.client.HTTPException, socket.timeout) as exc:
            raise OllamaProviderError(AI_PROVIDER_UNAVAILABLE) from exc
        finally:
            connection.close()
        if len(raw) > max_response_bytes:
            raise OllamaProviderError(AI_RESPONSE_TOO_LARGE)
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OllamaProviderError(AI_RESPONSE_INVALID) from exc
        return OllamaHttpResponse(response.status, parsed)


class OllamaAIProvider:
    """Ollama provider returning untrusted AIActionPlan-shaped data."""

    def __init__(self, config: OllamaProviderConfig, transport=None):
        self.config = config
        self.transport = transport or OllamaHttpTransport()

    def generate_plan(self, context):
        request = self.build_request(context)
        request_bytes = len(json.dumps(request, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        if request_bytes > self.config.maximum_request_bytes:
            raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)
        response = self.transport.post_json(
            self.config.host,
            self.config.port,
            OLLAMA_CHAT_PATH,
            request,
            self.config.timeout_seconds,
            self.config.maximum_response_bytes,
        )
        self._raise_for_status(response)
        return self._extract_structured_plan(response.body)

    def build_request(self, context):
        return {
            "model": self.config.model,
            "think": False,
            "stream": False,
            "format": ai_action_plan_schema(),
            "options": {
                "num_predict": self.config.maximum_output_tokens,
                "temperature": 0,
            },
            "messages": [
                {"role": "system", "content": _system_instruction()},
                {"role": "user", "content": _build_user_content(context)},
            ],
        }

    def _raise_for_status(self, response):
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 404:
            raise OllamaProviderError(AI_MODEL_NOT_FOUND)
        if status == 408:
            raise OllamaProviderError(AI_PROVIDER_TIMEOUT)
        if status == 413:
            raise OllamaProviderError(AI_RESPONSE_TOO_LARGE)
        if status in {500, 502, 503, 504}:
            raise OllamaProviderError(AI_MODEL_UNAVAILABLE)
        raise OllamaProviderError(AI_PROVIDER_PROTOCOL_ERROR)

    def _extract_structured_plan(self, body):
        if not isinstance(body, dict):
            raise OllamaProviderError(AI_RESPONSE_INVALID)
        message = body.get("message")
        if not isinstance(message, dict):
            raise OllamaProviderError(AI_RESPONSE_INVALID)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaProviderError(AI_RESPONSE_INVALID)
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaProviderError(AI_RESPONSE_INVALID) from exc
        if not isinstance(payload, dict):
            raise OllamaProviderError(AI_RESPONSE_INVALID)
        return payload


def _system_instruction() -> str:
    return (
        "You are JarvisOS local planning middleware. Return only JSON matching "
        "the provided AIActionPlan schema. canonical_command_text must use exact "
        "JarvisOS English command grammar. Do not invent devices or capabilities. "
        "Do not include chain-of-thought."
    )


def _build_user_content(context) -> str:
    return json.dumps(
        {
            "user_request": context.user_request,
            "safe_context": {
                "schema_version": context.schema_version,
                "devices": [_device_payload(device) for device in context.devices],
                "command_grammar": [dict(item) for item in context.command_grammar],
                "policies": {
                    "max_plan_steps": context.policies.max_plan_steps,
                    "confirmation_required_for_mutations": (
                        context.policies.confirmation_required_for_mutations
                    ),
                },
            },
            "allowed_plan_kinds": [PLAN_KIND_CLARIFY, PLAN_KIND_EXECUTE, PLAN_KIND_REFUSE],
            "limits": {
                "max_steps": MAX_PLAN_STEPS,
                "max_command_length": MAX_COMMAND_LENGTH,
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )


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


def _require_model(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Ollama model is required")
    if any(ch.isspace() for ch in model) or len(model) > 128:
        raise ValueError("Ollama model is invalid")


def _require_int(value: int, label: str, *, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"Ollama {label} is invalid")
