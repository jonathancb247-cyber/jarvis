"""Local Gemma understanding provider for hint-only extraction."""

from __future__ import annotations

from dataclasses import dataclass
import json

from jarvis_core.ai.contracts import (
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
    MAX_SAFE_TEXT_LENGTH,
)
from jarvis_core.ai.gemma_local import (
    DEFAULT_GEMMA_MAXIMUM_REQUEST_BYTES,
    DEFAULT_GEMMA_MAXIMUM_RESPONSE_BYTES,
    DEFAULT_GEMMA_TIMEOUT_SECONDS,
    GemmaLocalProviderError,
    GemmaLocalResponse,
    GemmaLocalTransport,
    UnconfiguredGemmaLocalTransport,
)
from jarvis_core.ai.understanding import UNDERSTANDING_FIELDS


DEFAULT_GEMMA_UNDERSTANDING_MAXIMUM_OUTPUT_TOKENS = 256


@dataclass(frozen=True)
class GemmaUnderstandingProviderConfig:
    """Immutable local Gemma understanding configuration."""

    model: str
    timeout_seconds: int = DEFAULT_GEMMA_TIMEOUT_SECONDS
    maximum_request_bytes: int = DEFAULT_GEMMA_MAXIMUM_REQUEST_BYTES
    maximum_response_bytes: int = DEFAULT_GEMMA_MAXIMUM_RESPONSE_BYTES
    maximum_output_tokens: int = DEFAULT_GEMMA_UNDERSTANDING_MAXIMUM_OUTPUT_TOKENS

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


class GemmaLocalUnderstandingProvider:
    """Gemma-backed provider returning untrusted understanding proposal data."""

    def __init__(
        self,
        config: GemmaUnderstandingProviderConfig,
        transport: GemmaLocalTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or UnconfiguredGemmaLocalTransport()

    def extract_understanding(self, context) -> object:
        request = self.build_request(context)
        request_bytes = len(
            json.dumps(
                request,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
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
        if actual_size > self.config.maximum_response_bytes:
            raise GemmaLocalProviderError(AI_RESPONSE_TOO_LARGE)
        if (
            response.body_size_bytes is not None
            and response.body_size_bytes > self.config.maximum_response_bytes
        ):
            raise GemmaLocalProviderError(AI_RESPONSE_TOO_LARGE)
        return self._extract_proposal(response.body)

    def build_request(self, context) -> dict[str, object]:
        return {
            "provider": "gemma-local-understanding",
            "model": self.config.model,
            "system_instruction": _system_instruction(),
            "input": _build_input(context),
            "response_format": {
                "type": "json_object",
                "fields": sorted(UNDERSTANDING_FIELDS),
            },
            "output_contract": {
                "authority": "hint_only",
                "allowed_fields": sorted(UNDERSTANDING_FIELDS),
                "no_runtime": True,
                "no_drivers": True,
                "no_ai_action_plan": True,
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

    def _extract_proposal(self, body):
        if isinstance(body, dict):
            if _looks_like_proposal(body):
                return body
            proposal = body.get("proposal")
            if isinstance(proposal, dict):
                return proposal
            text = _first_text_value(body, ("output_text", "text", "content"))
            if text is not None:
                return _parse_exact_json_object(text)
            raise GemmaLocalProviderError(AI_RESPONSE_INVALID)
        if isinstance(body, str):
            return _parse_exact_json_object(body)
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID)


def _system_instruction() -> str:
    return (
        "You are JarvisOS local understanding middleware. Extract hints only. "
        "Return one strict JSON object using only these fields: intent, "
        "referenced_device_text, referenced_device_id, capability_hint, "
        "operation_hint, raw_arguments, safety_hints, confidence, "
        "safe_explanation. Do not output AIActionPlan. Do not choose final "
        "execute, clarify or refuse authority. Do not call tools. Do not invent "
        "devices, capabilities or arguments that are not in the provided safe "
        "context or user request. Confidence and safety hints are diagnostic "
        "metadata only. Use null for unknown optional fields and [] for empty "
        "lists. Do not include chain-of-thought or prose outside JSON."
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
    try:
        if isinstance(response.body, str):
            return len(response.body.encode("utf-8"))
        return len(
            json.dumps(
                response.body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as error:
        raise GemmaLocalProviderError(AI_RESPONSE_INVALID) from error


def _looks_like_proposal(value: dict[str, object]) -> bool:
    return "intent" in value


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


def _require_model(model: str) -> None:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Gemma understanding model is required")
    if len(model) > 128 or any(ch in model for ch in "\r\n\t"):
        raise ValueError("Gemma understanding model is invalid")


def _require_int(value: int, label: str, *, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"Gemma understanding {label} is invalid")


__all__ = [
    "DEFAULT_GEMMA_UNDERSTANDING_MAXIMUM_OUTPUT_TOKENS",
    "GemmaLocalUnderstandingProvider",
    "GemmaUnderstandingProviderConfig",
]
