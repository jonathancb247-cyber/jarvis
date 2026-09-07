"""Provider-neutral understanding contracts for local AI role splitting."""

from dataclasses import dataclass, field
from typing import Protocol

from jarvis_core.ai.contracts import AI_RESPONSE_INVALID, MAX_SAFE_TEXT_LENGTH
from jarvis_core.ai.validation import AIValidationError


UNDERSTANDING_FIELDS = {
    "intent",
    "referenced_device_text",
    "referenced_device_id",
    "capability_hint",
    "operation_hint",
    "raw_arguments",
    "safety_hints",
    "confidence",
    "safe_explanation",
}
MAX_UNDERSTANDING_ARGUMENTS = 16
MAX_UNDERSTANDING_HINTS = 8
MAX_UNDERSTANDING_TEXT_LENGTH = MAX_SAFE_TEXT_LENGTH


@dataclass(frozen=True)
class AIUnderstandingProposal:
    """Untrusted local-model extraction proposal.

    The proposal is input to deterministic resolution only. Its intent, safety
    hints and confidence are never authority for execute/clarify/refuse.
    """

    intent: str
    referenced_device_text: str = None
    referenced_device_id: str = None
    capability_hint: str = None
    operation_hint: str = None
    raw_arguments: tuple = field(default_factory=tuple)
    safety_hints: tuple = field(default_factory=tuple)
    confidence: float = None
    safe_explanation: str = ""

    def __post_init__(self):
        _require_bounded_string(self.intent, "AIUnderstandingProposal intent")
        _validate_optional_string(
            self.referenced_device_text,
            "referenced_device_text",
        )
        _validate_optional_string(self.referenced_device_id, "referenced_device_id")
        _validate_optional_string(self.capability_hint, "capability_hint")
        _validate_optional_string(self.operation_hint, "operation_hint")
        if not isinstance(self.raw_arguments, tuple):
            raise ValueError("raw_arguments must be a tuple")
        if len(self.raw_arguments) > MAX_UNDERSTANDING_ARGUMENTS:
            raise ValueError("raw_arguments has too many items")
        for item in self.raw_arguments:
            if not (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], str)
            ):
                raise ValueError("raw_arguments must contain string pairs")
            _require_bounded_string(item[0], "raw argument name", 128)
            _require_bounded_string(item[1], "raw argument value")
        if not isinstance(self.safety_hints, tuple):
            raise ValueError("safety_hints must be a tuple")
        if len(self.safety_hints) > MAX_UNDERSTANDING_HINTS:
            raise ValueError("safety_hints has too many items")
        for hint in self.safety_hints:
            _require_bounded_string(hint, "safety hint")
        if self.confidence is not None:
            if not isinstance(self.confidence, (int, float)):
                raise ValueError("confidence must be numeric")
            if not 0.0 <= float(self.confidence) <= 1.0:
                raise ValueError("confidence must be between 0 and 1")
        if self.safe_explanation:
            _require_bounded_string(self.safe_explanation, "safe_explanation")


class AIUnderstandingProvider(Protocol):
    """Extract bounded understanding data from a detached safe context."""

    def extract_understanding(self, context) -> object:
        ...


def normalize_understanding_proposal(payload):
    """Normalize untrusted provider output into an AIUnderstandingProposal."""
    if not isinstance(payload, dict):
        raise AIValidationError(AI_RESPONSE_INVALID)
    unknown = set(payload) - UNDERSTANDING_FIELDS
    if unknown:
        raise AIValidationError(AI_RESPONSE_INVALID)
    try:
        return AIUnderstandingProposal(
            intent=payload["intent"],
            referenced_device_text=_optional_text(payload.get("referenced_device_text")),
            referenced_device_id=_optional_text(payload.get("referenced_device_id")),
            capability_hint=_optional_text(payload.get("capability_hint")),
            operation_hint=_optional_text(payload.get("operation_hint")),
            raw_arguments=_normalize_arguments(payload.get("raw_arguments", ())),
            safety_hints=_normalize_string_list(payload.get("safety_hints", ())),
            confidence=_normalize_confidence(payload.get("confidence")),
            safe_explanation=_optional_text(payload.get("safe_explanation")) or "",
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AIValidationError(AI_RESPONSE_INVALID) from error


def _normalize_arguments(value):
    if value is None:
        return ()
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        raise ValueError("raw_arguments must be a mapping or list")

    normalized = []
    seen_keys = set()
    for item in items:
        if isinstance(item, tuple) and len(item) == 2:
            key, raw_value = item
        elif isinstance(item, list) and len(item) == 2:
            key, raw_value = item
        else:
            raise ValueError("raw_arguments entries must be pairs")
        normalized_key = _text(key, 128)
        if normalized_key in seen_keys:
            raise ValueError("raw_arguments contains duplicate keys")
        seen_keys.add(normalized_key)
        normalized.append((normalized_key, _text(raw_value, MAX_SAFE_TEXT_LENGTH)))
    if len(normalized) > MAX_UNDERSTANDING_ARGUMENTS:
        raise ValueError("raw_arguments has too many items")
    return tuple(normalized)


def _normalize_string_list(value):
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("string list must be a list or tuple")
    if len(value) > MAX_UNDERSTANDING_HINTS:
        raise ValueError("string list has too many items")
    return tuple(_text(item, MAX_SAFE_TEXT_LENGTH) for item in value)


def _normalize_confidence(value):
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ValueError("confidence must be numeric")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return confidence


def _optional_text(value):
    if value is None:
        return None
    return _text(value, MAX_SAFE_TEXT_LENGTH)


def _text(value, max_length):
    if not isinstance(value, str):
        raise ValueError("value must be a string")
    text = "".join(ch for ch in value if ch >= " " and ch != "\x7f").strip()
    if not text:
        raise ValueError("value must be non-empty")
    if len(text) > max_length:
        raise ValueError("value exceeds maximum length")
    return text


def _require_bounded_string(value, label, max_length=MAX_UNDERSTANDING_TEXT_LENGTH):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > max_length:
        raise ValueError(f"{label} exceeds maximum length")


def _validate_optional_string(value, label):
    if value is not None:
        _require_bounded_string(value, label)
