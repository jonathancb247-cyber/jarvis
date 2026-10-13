"""Authenticated, strictly non-executing local interaction endpoint support.

This module adapts the existing, provider-neutral interaction boundary
(``handle_interaction`` / ``describe_interaction``) to an HTTP-facing service for
the optional Runtime API. It is deliberately independent from Runtime, Drivers,
the Planner, the ExecutionGate, confirmation stores and transports:

- it reuses the existing ``SafeContextBuilder``, an injected local understanding
  provider and the existing ``DeterministicUnderstandingResolver``;
- it always builds the safe context and permissions server-side from the
  injected ``DeviceRegistry``; a client can never supply context, a decision,
  a plan or permissions;
- every response keeps ``commands_executed`` false, and no command is ever
  constructed, confirmed or dispatched here;
- provider failure categories are preserved and mapped to explicit HTTP
  statuses instead of being rewritten into successful conversations.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from threading import BoundedSemaphore
from time import perf_counter

from jarvis_core.ai.context import SafeContextBuilder
from jarvis_core.ai.contracts import (
    AI_PROVIDER_TIMEOUT,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
    AI_PROVIDER_PROTOCOL_ERROR,
)
from jarvis_core.ai.interaction import (
    INTERACTION_TYPE_CONVERSATION,
    describe_interaction,
    handle_interaction,
)
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    LOCAL_AI_UNAVAILABLE,
    NEEDS_CLARIFICATION,
    REFUSED,
    UNDERSTANDING_FAILED,
)
from jarvis_core.ai.understanding_resolution import DeterministicUnderstandingResolver
from jarvis_core.api import errors


INTERACTION_OK_STATUS = 200
INTERACTION_PROVIDER_INVALID_STATUS = 502
INTERACTION_PROVIDER_UNAVAILABLE_STATUS = 503
INTERACTION_PROVIDER_TIMEOUT_STATUS = 504

DEFAULT_MAX_CONCURRENCY = 2
# A bearer token must be long enough to resist trivial guessing and is restricted
# to printable ASCII without whitespace so it survives HTTP header framing intact.
MIN_INTERACTION_TOKEN_LENGTH = 16

_TERMINAL_DECISION_STATUSES = frozenset(
    {EXECUTABLE_CANDIDATE, NEEDS_CLARIFICATION, REFUSED}
)
_INVALID_RESPONSE_CATEGORIES = frozenset(
    {AI_RESPONSE_INVALID, AI_RESPONSE_TOO_LARGE, AI_PROVIDER_PROTOCOL_ERROR}
)


@dataclass(frozen=True)
class InteractionResponse:
    """Detached HTTP status and JSON-safe body for one interaction turn."""

    status: int
    body: dict


class InteractionAuth:
    """Constant-time Bearer token check that fails closed when unconfigured."""

    def __init__(self, token):
        if not isinstance(token, str) or not token:
            raise ValueError("an interaction bearer token is required")
        if not token.isascii() or not token.isprintable():
            raise ValueError("interaction bearer token must be printable ASCII")
        if any(character.isspace() for character in token):
            raise ValueError("interaction bearer token must not contain whitespace")
        if len(token) < MIN_INTERACTION_TOKEN_LENGTH:
            raise ValueError(
                "interaction bearer token must be at least "
                f"{MIN_INTERACTION_TOKEN_LENGTH} characters"
            )
        self._token = token

    def authorize(self, header_value):
        """Return None when the header carries the expected bearer token.

        Malformed or non-ASCII headers fail closed with 401 and never surface as
        an internal error: comparison is only attempted for printable ASCII
        input, which keeps constant-time comparison valid.
        """
        if not isinstance(header_value, str) or not header_value.isascii():
            raise errors.unauthorized()
        parts = header_value.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise errors.unauthorized()
        candidate = parts[1]
        if not candidate.isascii() or not hmac.compare_digest(candidate, self._token):
            raise errors.unauthorized()


class LocalInteractionService:
    """Run one non-executing interaction with bounded, fail-fast concurrency."""

    def __init__(
        self,
        device_registry,
        provider,
        *,
        provider_id,
        model_id,
        context_builder=None,
        resolver=None,
        max_concurrency=DEFAULT_MAX_CONCURRENCY,
        clock=perf_counter,
    ):
        if not callable(getattr(provider, "extract_understanding", None)):
            raise TypeError(
                "LocalInteractionService requires an understanding provider"
            )
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider_id is required")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id is required")
        if not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive int")
        self._device_registry = device_registry
        self._provider = provider
        self._provider_id = provider_id
        self._model_id = model_id
        self._context_builder = context_builder or SafeContextBuilder()
        self._resolver = resolver or DeterministicUnderstandingResolver()
        self._clock = clock
        self._capacity = BoundedSemaphore(max_concurrency)

    def handle(self, message):
        """Return an :class:`InteractionResponse` for a validated message.

        Concurrency is bounded without an unbounded queue: when no slot is
        available the request fails fast with a busy error instead of waiting.
        """
        if not self._capacity.acquire(blocking=False):
            raise errors.interaction_busy()
        try:
            result = self._run(message)
        finally:
            self._capacity.release()
        return _response_for(result)

    def _run(self, message):
        context = self._context_builder.build(message, self._device_registry)
        if getattr(context, "user_request", None) != message:
            raise errors.request_invalid(
                "Interaction message cannot be preserved literally."
            )
        return handle_interaction(
            message,
            provider=self._provider,
            context=context,
            provider_id=self._provider_id,
            model_id=self._model_id,
            resolver=self._resolver,
            clock=self._clock,
        )


def _response_for(result):
    status, code = _status_for(result)
    body = describe_interaction(result)
    body["success"] = status < 400
    body["error"] = code
    return InteractionResponse(status=status, body=body)


def _status_for(result):
    if result.type == INTERACTION_TYPE_CONVERSATION:
        return INTERACTION_OK_STATUS, None
    decision = result.decision
    if decision is not None and decision.status in _TERMINAL_DECISION_STATUSES:
        return INTERACTION_OK_STATUS, None
    if decision is not None and decision.status == LOCAL_AI_UNAVAILABLE:
        return (
            INTERACTION_PROVIDER_UNAVAILABLE_STATUS,
            errors.API_INTERACTION_PROVIDER_UNAVAILABLE,
        )
    if decision is not None and decision.status == UNDERSTANDING_FAILED:
        if decision.failure_category == AI_PROVIDER_TIMEOUT:
            return (
                INTERACTION_PROVIDER_TIMEOUT_STATUS,
                errors.API_INTERACTION_PROVIDER_TIMEOUT,
            )
        if decision.failure_category in _INVALID_RESPONSE_CATEGORIES:
            return (
                INTERACTION_PROVIDER_INVALID_STATUS,
                errors.API_INTERACTION_PROVIDER_INVALID,
            )
    return (
        INTERACTION_PROVIDER_INVALID_STATUS,
        errors.API_INTERACTION_PROVIDER_INVALID,
    )


__all__ = [
    "DEFAULT_MAX_CONCURRENCY",
    "MIN_INTERACTION_TOKEN_LENGTH",
    "INTERACTION_OK_STATUS",
    "INTERACTION_PROVIDER_INVALID_STATUS",
    "INTERACTION_PROVIDER_TIMEOUT_STATUS",
    "INTERACTION_PROVIDER_UNAVAILABLE_STATUS",
    "InteractionAuth",
    "InteractionResponse",
    "LocalInteractionService",
]
