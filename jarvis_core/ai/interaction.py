"""Deterministic, non-executing interaction entry point for JarvisOS.

This module is the minimal first increment of safe interaction. It recognizes a
small whitelist of *pure* greetings and answers them with a fixed conversation
response without calling any provider. Every other message, including a greeting
that is accompanied by an instruction, is delegated verbatim to the existing
``decide_understanding()`` boundary.

Boundaries honored here:

- ``decide_understanding()`` and its ``DeterministicUnderstandingResolver`` plus
  the existing Planner/validation boundary remain the sole resolution authority.
  This module does not duplicate the Planner, the resolver, or the ExecutionGate.
- This module never imports Runtime, Drivers, the Planner, the resolver, the
  ExecutionGate, confirmation stores, adapters, transports, or any provider.
- No command is ever constructed, confirmed, or dispatched from here.
- A decision produced by a client is never trusted: this module always computes
  its own ``LocalUnderstandingDecision`` and never accepts a decision argument.

Eventual ``action_candidate`` semantics: an ``executable_candidate`` status is
only a validated candidate that would still require the normal confirmation and
policy path before any execution. It is never authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
import re
import unicodedata

from jarvis_core.ai.contracts import MAX_USER_REQUEST_LENGTH
from jarvis_core.ai.understanding_decision import (
    LocalUnderstandingDecision,
    decide_understanding,
)
from jarvis_core.ai.understanding_diagnostic import describe_decision

INTERACTION_SCHEMA_VERSION = 1

INTERACTION_TYPE_CONVERSATION = "conversation"
INTERACTION_TYPE_UNDERSTANDING = "understanding"
INTERACTION_TYPES = frozenset(
    {INTERACTION_TYPE_CONVERSATION, INTERACTION_TYPE_UNDERSTANDING}
)

COMMANDS_EXECUTED = False

MAX_INTERACTION_MESSAGE_LENGTH = MAX_USER_REQUEST_LENGTH

# A deliberately small whitelist of *pure* greetings keyed by their normalized
# spelling. Any message that is not exactly one of these keys is delegated so
# the deterministic boundary decides execute/clarify/refuse.
_GREETING_RESPONSES = {
    "hola": "Hola. ¿En qué puedo ayudarte?",
    "hola jarvis": "Hola. ¿En qué puedo ayudarte?",
    "hey jarvis": "Hola. ¿En qué puedo ayudarte?",
    "buenas": "Hola. ¿En qué puedo ayudarte?",
    "buenos dias": "Buenos días. ¿En qué puedo ayudarte?",
    "buenas tardes": "Buenas tardes. ¿En qué puedo ayudarte?",
    "buenas noches": "Buenas noches. ¿En qué puedo ayudarte?",
}

PURE_GREETINGS = frozenset(_GREETING_RESPONSES)

# Outer punctuation is stripped for greeting matching. Quotes are intentionally
# excluded so a quoted greeting (a citation) is never intercepted as a greeting.
_EDGE_PUNCTUATION = " \t\r\n.,;:!?¿¡()[]{}<>«»—–-…"
_INTERIOR_SEPARATORS = re.compile(r"[,;:]+")


@dataclass(frozen=True)
class InteractionResult:
    """Immutable, non-executing outcome of one interaction turn."""

    schema_version: int
    type: str
    response_text: str
    decision: LocalUnderstandingDecision | None = None
    commands_executed: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != INTERACTION_SCHEMA_VERSION:
            raise ValueError("interaction schema_version is unsupported")
        if self.type not in INTERACTION_TYPES:
            raise ValueError("interaction type is invalid")
        if not isinstance(self.response_text, str):
            raise ValueError("interaction response_text must be a string")
        if self.decision is not None and not isinstance(
            self.decision,
            LocalUnderstandingDecision,
        ):
            raise ValueError("interaction decision is invalid")
        if self.commands_executed is not False:
            raise ValueError("an interaction result never executes commands")
        if self.type == INTERACTION_TYPE_CONVERSATION:
            if self.decision is not None:
                raise ValueError("conversation results cannot carry a decision")
            if not self.response_text.strip():
                raise ValueError("conversation results require a response_text")
        elif self.decision is None:
            raise ValueError("understanding results require a decision")


def normalize_greeting(text: str) -> str:
    """Normalize a candidate greeting without removing meaningful content.

    Case, accents, repeated whitespace and *outer* punctuation are normalized;
    interior separator punctuation (``,`` ``;`` ``:``) is collapsed. Quotes are
    preserved so a quoted greeting is not mistaken for a greeting.
    """
    if not isinstance(text, str):
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.casefold().strip()
    normalized = normalized.strip(_EDGE_PUNCTUATION).strip()
    normalized = _INTERIOR_SEPARATORS.sub(" ", normalized)
    return " ".join(normalized.split())


def match_greeting(text: str) -> str | None:
    """Return the canonical greeting key for a pure greeting, else ``None``.

    Only an exact whitelist match counts, so a greeting that carries any extra
    instruction, negation, quote or content is never intercepted here.
    """
    key = normalize_greeting(text)
    if key in _GREETING_RESPONSES:
        return key
    return None


def handle_interaction(
    message: str,
    *,
    provider=None,
    context=None,
    provider_id: str | None = None,
    model_id: str | None = None,
    resolver=None,
    clock=perf_counter,
) -> InteractionResult:
    """Answer a pure greeting or delegate a message to local understanding.

    Pure greetings return a ``conversation`` result and never call the provider.
    Any other message returns an ``understanding`` result carrying the
    ``LocalUnderstandingDecision`` produced by the existing
    ``decide_understanding()`` boundary. The complete original ``message`` is
    delegated; it is never trimmed or rewritten. This function never executes
    commands.
    """
    _require_message(message)

    key = match_greeting(message)
    if key is not None:
        return InteractionResult(
            schema_version=INTERACTION_SCHEMA_VERSION,
            type=INTERACTION_TYPE_CONVERSATION,
            response_text=_GREETING_RESPONSES[key],
            decision=None,
            commands_executed=COMMANDS_EXECUTED,
        )

    decision = _delegate_understanding(
        message,
        provider=provider,
        context=context,
        provider_id=provider_id,
        model_id=model_id,
        resolver=resolver,
        clock=clock,
    )
    return InteractionResult(
        schema_version=INTERACTION_SCHEMA_VERSION,
        type=INTERACTION_TYPE_UNDERSTANDING,
        response_text="",
        decision=decision,
        commands_executed=COMMANDS_EXECUTED,
    )


def describe_interaction(result: InteractionResult) -> dict[str, object]:
    """Return a JSON-safe, bounded projection of an interaction result.

    The embedded decision is projected through the existing safe decision
    diagnostic, so canonical command text stays hidden by default. The
    projection never contains raw model output and always reports
    ``commands_executed`` as false.
    """
    payload: dict[str, object] = {
        "schema_version": result.schema_version,
        "type": result.type,
        "response_text": result.response_text,
        "commands_executed": result.commands_executed,
        "decision": None,
    }
    if result.decision is not None:
        payload["decision"] = describe_decision(result.decision)
    return payload


def _delegate_understanding(
    message: str,
    *,
    provider,
    context,
    provider_id,
    model_id,
    resolver,
    clock,
) -> LocalUnderstandingDecision:
    if provider is None:
        raise ValueError("a provider is required to delegate a non-greeting message")
    if context is None:
        raise ValueError("a context is required to delegate a non-greeting message")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("provider_id is required to delegate a non-greeting message")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model_id is required to delegate a non-greeting message")
    if getattr(context, "user_request", None) != message:
        raise ValueError(
            "context.user_request must be the complete interaction message"
        )
    return decide_understanding(
        provider,
        context,
        provider_id=provider_id,
        model_id=model_id,
        resolver=resolver,
        clock=clock,
    )


def _require_message(message: str) -> None:
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")
    if len(message) > MAX_INTERACTION_MESSAGE_LENGTH:
        raise ValueError("message exceeds the maximum interaction length")


__all__ = [
    "COMMANDS_EXECUTED",
    "INTERACTION_SCHEMA_VERSION",
    "INTERACTION_TYPE_CONVERSATION",
    "INTERACTION_TYPE_UNDERSTANDING",
    "INTERACTION_TYPES",
    "MAX_INTERACTION_MESSAGE_LENGTH",
    "PURE_GREETINGS",
    "InteractionResult",
    "describe_interaction",
    "handle_interaction",
    "match_greeting",
    "normalize_greeting",
]
