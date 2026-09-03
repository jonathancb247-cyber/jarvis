"""Fake-first local Gemma provider boundary for AIActionPlan-shaped output."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

from jarvis_core.ai.contracts import (
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


DEFAULT_GEMMA_TIMEOUT_SECONDS = 60
DEFAULT_GEMMA_MAXIMUM_REQUEST_BYTES = 24 * 1024
DEFAULT_GEMMA_MAXIMUM_RESPONSE_BYTES = 64 * 1024
DEFAULT_GEMMA_MAXIMUM_OUTPUT_TOKENS = 512


class GemmaLocalProviderError(AIValidationError):
    """Safe local Gemma provider error."""


@dataclass(frozen=True)
class GemmaLocalProviderConfig:
    """Immutable local Gemma adapter-layer configuration."""

    model: str
    timeout_seconds: int = DEFAULT_GEMMA_TIMEOUT_SECONDS
    maximum_request_bytes: int = DEFAULT_GEMMA_MAXIMUM_REQUEST_BYTES
    maximum_response_bytes: int = DEFAULT_GEMMA_MAXIMUM_RESPONSE_BYTES
    maximum_output_tokens: int = DEFAULT_GEMMA_MAXIMUM_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        _require_model(self.model)
        _require_int(self.timeout_seconds, "timeout_seconds", minimum=1, maximum=180)
        _require_int(
            self.maximum_request_bytes,
            "maximum_request_bytes",
            minimum=1024,
            maximum=256 * 1024,
        )
        _require_int(
            self.maximum_response_bytes,
            "maximum_response_bytes",
            minimum=1024,
            maximum=512 * 1024,
        )
        _require_int(
            self.maximum_output_tokens,
            "maximum_output_tokens",
            minimum=1,
            maximum=4096,
        )


@dataclass(frozen=True)
class GemmaLocalResponse:
    """Detached response envelope returned by an injected local Gemma transport."""

    body: object
    body_size_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.body_size_bytes is not None and (
            not isinstance(self.body_size_bytes, int) or self.body_size_bytes < 0
        ):
            raise ValueError("Gemma body_size_bytes is invalid")


class GemmaLocalTransport(Protocol):
    """Minimal host/bridge contract for future local Gemma execution."""

    def generate(
        self,
        request: dict[str, object],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> GemmaLocalResponse:
        ...


class UnconfiguredGemmaLocalTransport:
    """Placeholder transport until an Edge Gallery or host bridge is approved."""

    def generate(
        self,
        request: dict[str, object],
        timeout_seconds: int,
        max_response_bytes: int,
    ) -> GemmaLocalResponse:
        raise GemmaLocalProviderError(AI_PROVIDER_UNAVAILABLE)


class GemmaLocalAIProvider:
    """Local Gemma provider returning untrusted AIActionPlan-shaped data."""

    def __init__(self, config: GemmaLocalProviderConfig, transport=None):
        self.config = config
        self.transport = transport or UnconfiguredGemmaLocalTransport()

    def generate_plan(self, context):
        request = self.build_request(context)
        request_bytes = len(
            json.dumps(request, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        )
        if request_bytes > self.config.maximum_request_bytes:
            raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR)
        try:
            response = self.transport.generate(
                request,
                self.config.timeout_seconds,
                self.config.maximum_response_bytes,
            )
        except GemmaLocalProviderError:
            raise
        except TimeoutError as error:
            raise GemmaLocalProviderError(AI_PROVIDER_TIMEOUT) from error
        except OSError as error:
            raise GemmaLocalProviderError(AI_PROVIDER_UNAVAILABLE) from error
        except Exception as error:
            raise GemmaLocalProviderError(AI_PROVIDER_UNAVAILABLE) from error

        if not isinstance(response, GemmaLocalResponse):
            raise GemmaLocalProviderError(AI_PROVIDER_PROTOCOL_ERROR)
        actual_size = _response_size_bytes(response)
        reported_size = response.body_size_bytes
        if actual_size > self.config.maximum_response_bytes:
            raise GemmaLocalProviderError(AI_RESPONSE_TOO_LARGE)
        if reported_size is not None and reported_size > self.config.maximum_response_bytes:
            raise GemmaLocalProviderError(AI_RESPONSE_TOO_LARGE)
        return self._extract_structured_plan(response.body)

    def build_request(self, context) -> dict[str, object]:
        return {
            "provider": "gemma-local",
            "model": self.config.model,
            "system_instruction": _system_instruction(),
            "input": _build_input(context),
            "response_format": {
                "type": "json_schema",
                "schema": ai_action_plan_schema(),
            },
            "generation_config": {
                "max_output_tokens": self.config.maximum_output_tokens,
                "temperature": 0,
            },
            "execution": {
                "tools": False,
                "runtime": False,
                "drivers": False,
            },
        }

    def _extract_structured_plan(self, body):
        if isinstance(body, dict):
            if _looks_like_plan(body):
                return body
            plan = body.get("plan")
            if isinstance(plan, dict):
                return plan
            tool_plan = _extract_tool_call_plan(body)
            if tool_plan is not None:
                return tool_plan
            text = _first_text_value(body, ("output_text", "text", "content"))
            if text is not None:
                return _parse_exact_json_object(text)
            raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
        if isinstance(body, str):
            return _parse_exact_json_object(body)
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)


def _system_instruction() -> str:
    return (
        "You are JarvisOS local Gemma planning middleware. Return only JSON "
        "matching the provided AIActionPlan schema. Do not include prose before "
        "or after the JSON. canonical_command_text must use exact JarvisOS "
        "English command grammar. Do not invent devices or capabilities. "
        f"If kind is execute, steps must contain 1..{MAX_PLAN_STEPS} executable "
        "steps, clarification must be null, and refusal must be null. "
        "If kind is clarify, steps must be [], clarification must be non-null, "
        "refusal must be null, and confirmation_required must be false. "
        "If kind is refuse, steps must be [], clarification must be null, "
        "refusal must be non-null, and confirmation_required must be false. "
        "If native tool calling is used by the local host, emit only an "
        "AIActionPlan-compatible payload; never call tools. "
        "Do not include chain-of-thought."
    )


def _build_input(context) -> dict[str, object]:
    return {
        "user_request": context.user_request,
        "safe_context": {
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
        },
        "allowed_plan_kinds": [PLAN_KIND_CLARIFY, PLAN_KIND_EXECUTE, PLAN_KIND_REFUSE],
        "limits": {
            "max_steps": MAX_PLAN_STEPS,
            "max_command_length": MAX_COMMAND_LENGTH,
        },
    }


def _device_payload(device) -> dict[str, object]:
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


def _response_size_bytes(response: GemmaLocalResponse) -> int:
    """Return the actual serialized body size (not the reported size)."""
    try:
        if isinstance(response.body, str):
            return len(response.body.encode("utf-8"))
        return len(json.dumps(response.body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID) from error


def _looks_like_plan(value: dict[str, object]) -> bool:
    return "schema_version" in value and "kind" in value


def _first_text_value(body: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = body.get(key)
        if isinstance(value, str):
            return value
    return None


def _parse_exact_json_object(text: str) -> dict[str, object]:
    if not isinstance(text, str) or not text.strip():
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
    text = text.strip()
    decoder = json.JSONDecoder()
    try:
        payload, end = decoder.raw_decode(text)
    except json.JSONDecodeError as error:
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID) from error
    if text[end:].strip():
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
    if not isinstance(payload, dict):
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
    return payload


def _extract_tool_call_plan(body: dict[str, object]) -> dict[str, object] | None:
    tool_calls = body.get("tool_calls")
    if isinstance(tool_calls, list):
        if len(tool_calls) != 1:
            raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
        return _tool_call_arguments(tool_calls[0])
    function_call = body.get("function_call")
    if isinstance(function_call, dict):
        return _tool_call_arguments(function_call)
    return None


def _tool_call_arguments(tool_call: object) -> dict[str, object] | None:
    if not isinstance(tool_call, dict):
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
    function = tool_call.get("function")
    source = function if isinstance(function, dict) else tool_call
    name = source.get("name")
    if name not in {"ai_action_plan", "jarvis_ai_action_plan"}:
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
    arguments = source.get("arguments")
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        return _parse_exact_json_object(arguments)
    raise GemmaLocalProviderError(AI_RESPONSE_INVALID)


def _require_model(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Gemma model is required")
    if len(model) > 128 or any(ch in model for ch in "\r\n\t"):
        raise ValueError("Gemma model is invalid")


def _require_int(value: int, label: str, *, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"Gemma {label} is invalid")


__all__ = [
    "DEFAULT_GEMMA_MAXIMUM_OUTPUT_TOKENS",
    "DEFAULT_GEMMA_MAXIMUM_REQUEST_BYTES",
    "DEFAULT_GEMMA_MAXIMUM_RESPONSE_BYTES",
    "DEFAULT_GEMMA_TIMEOUT_SECONDS",
    "GemmaLocalAIProvider",
    "GemmaLocalProviderConfig",
    "GemmaLocalProviderError",
    "GemmaLocalResponse",
    "GemmaLocalTransport",
    "UnconfiguredGemmaLocalTransport",
]
