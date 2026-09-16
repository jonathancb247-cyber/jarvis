"""Deterministic resolution for local AI understanding proposals."""

import re
import unicodedata

from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
    ACTION_KIND_READ,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
    PLAN_SCHEMA_VERSION,
)
from jarvis_core.ai.understanding import AIUnderstandingProposal
from jarvis_core.ai.validation import (
    classify_command,
    normalize_plan,
    recompute_plan,
    recompute_step,
    validate_against_context,
    validate_command_text_safety,
    validate_plan_shape,
    validate_with_planner,
)
from jarvis_core.planner import Planner


DESTRUCTIVE_PATTERN = re.compile(
    r"\b("
    r"delete|remove|erase|destroy|wipe|format|"
    r"borra\w*|elimina\w*|destruy\w*|formatea\w*"
    r")\b",
    re.IGNORECASE,
)
DESTRUCTIVE_TERMS = {
    "delete",
    "remove",
    "erase",
    "destroy",
    "wipe",
    "format",
    "borrar",
    "eliminar",
    "destruir",
    "formatear",
}
POWER_SWITCH_ON_VERBS = {
    "enciende",
    "encender",
    "prende",
    "prender",
}
POWER_SWITCH_OFF_VERBS = {
    "apaga",
    "apagar",
}
POWER_SWITCH_ON_PHRASES = {
    ("turn", "on"),
    ("switch", "on"),
}
POWER_SWITCH_OFF_PHRASES = {
    ("turn", "off"),
    ("switch", "off"),
}
TRUE_VALUES = {"true", "on"}
FALSE_VALUES = {"false", "off"}
NEGATION_TERMS = {"no", "not", "dont", "don", "do", "never", "nunca"}
QUESTION_TERMS = {"is", "esta", "estan"}
READ_STATUS_TERMS = {
    "status",
    "estado",
}
DEVICE_TEXT_SYNONYMS = {
    "light": {"light", "lights", "luz", "luces", "lampara", "lamp", "lamps"},
    "lamp": {"light", "lights", "luz", "luces", "lampara", "lamp", "lamps"},
    "luz": {"light", "lights", "luz", "luces", "lampara", "lamp", "lamps"},
    "luces": {"light", "lights", "luz", "luces", "lampara", "lamp", "lamps"},
    "lampara": {"light", "lights", "luz", "luces", "lampara", "lamp", "lamps"},
}
LOCATIVE_PREPOSITIONS = {
    "de",
    "del",
    "en",
    "al",
    "desde",
    "in",
    "at",
    "near",
    "on",
    "by",
    "inside",
}
LOCATIVE_ARTICLES = {
    "el",
    "la",
    "los",
    "las",
    "lo",
    "un",
    "una",
    "unos",
    "unas",
    "the",
    "a",
    "an",
    "del",
    "al",
}
DEVICE_ROLE_ANCHOR_TERMS = ("dispositivo", "dispositivos", "device", "devices")
ENTITY_BOUNDARY_BEFORE_TERMS = frozenset(
    set(LOCATIVE_PREPOSITIONS)
    | set(LOCATIVE_ARTICLES)
    | POWER_SWITCH_ON_VERBS
    | POWER_SWITCH_OFF_VERBS
    | {
        "turn",
        "switch",
        "please",
        "of",
        "my",
        "your",
        "our",
        "their",
        "his",
        "her",
        "its",
        "this",
        "that",
        "these",
        "those",
    }
)
ENTITY_BOUNDARY_AFTER_TERMS = frozenset(
    set(LOCATIVE_PREPOSITIONS)
    | set(LOCATIVE_ARTICLES)
    | {"please"}
)


class DeterministicUnderstandingResolver:
    """Resolve hint-only understanding into a validated non-executed plan."""

    def __init__(self, planner=None):
        self.planner = planner or Planner()

    def resolve(self, safe_context, proposal):
        raw_plan = self.resolve_to_raw_plan(safe_context, proposal)
        plan = validate_plan_shape(normalize_plan(raw_plan))
        if plan.kind != PLAN_KIND_EXECUTE:
            return plan
        step = plan.steps[0]
        validate_command_text_safety(step.canonical_command_text)
        command = validate_with_planner(self.planner, step.canonical_command_text)
        validate_against_context(step, command, safe_context)
        action_kind = classify_command(command, safe_context)
        return recompute_plan(plan, (recompute_step(step, action_kind),))

    def refusal_precheck(self, safe_context):
        """Return a validated refuse plan for destructive requests.

        This never depends on model proposal normalization. Destructive
        requests refuse with forbidden_operation before any proposal value
        is trusted; non-destructive requests return None so downstream
        behavior stays fail-closed.
        """
        if not _is_destructive_request(safe_context.user_request):
            return None
        raw_plan = _refuse_plan("forbidden_operation", "That request is not allowed.")
        return validate_plan_shape(normalize_plan(raw_plan))

    def resolve_to_raw_plan(self, safe_context, proposal):
        if not isinstance(proposal, AIUnderstandingProposal):
            raise TypeError("proposal must be an AIUnderstandingProposal")
        if _is_destructive_request(safe_context.user_request):
            return _refuse_plan("forbidden_operation", "That request is not allowed.")

        candidates = _resolve_device_candidates(safe_context, proposal)
        if proposal.referenced_device_id and not candidates:
            return _clarify_plan(
                "insufficient_context",
                "I could not find that device.",
                ("device_id",),
                (),
            )
        if not candidates:
            return _clarify_plan(
                "insufficient_context",
                "Which device should I use?",
                ("device_id",),
                (),
            )
        if len(candidates) > 1:
            return _clarify_plan(
                "ambiguous_device",
                "Which device did you mean?",
                ("device_id",),
                tuple(device.device_id for device in candidates[:5]),
            )

        device = candidates[0]
        if not _capability_hint_is_grounded(
            safe_context.user_request,
            proposal.capability_hint,
        ):
            return _clarify_plan(
                "unsupported_request",
                "That capability was not clearly requested.",
                ("capability_name",),
                tuple(capability.name for capability in device.capabilities[:5]),
            )
        capability = _find_capability(device, proposal.capability_hint)
        if capability is None:
            return _clarify_plan(
                "unsupported_request",
                "That capability is not available for the resolved device.",
                ("capability_name",),
                tuple(capability.name for capability in device.capabilities[:5]),
            )

        try:
            arguments = _arguments_as_dict(proposal.raw_arguments)
        except ValueError:
            return _clarify_plan(
                "missing_parameter",
                "A required parameter is missing.",
                ("parameters",),
                (),
            )
        if capability.kind == "reading":
            return _execute_plan(
                f"device read {device.device_id} {capability.name}",
                device.device_id,
                capability.name,
                ACTION_KIND_READ,
            )

        missing = _missing_required_arguments(arguments, capability)
        if missing:
            return _clarify_plan(
                "missing_parameter",
                "A required parameter is missing.",
                tuple(missing),
                (),
            )
        ungrounded = _ungrounded_arguments(
            safe_context.user_request,
            arguments,
            capability,
        )
        if ungrounded:
            return _clarify_plan(
                "missing_parameter",
                "A required parameter is missing.",
                tuple(ungrounded),
                (),
            )

        command = " ".join(
            [
                "device",
                "apply",
                device.device_id,
                capability.name,
                *[f"{key}={arguments[key]}" for key in sorted(arguments)],
            ]
        )
        return _execute_plan(
            command,
            device.device_id,
            capability.name,
            ACTION_KIND_MUTATE,
        )


def _resolve_device_candidates(safe_context, proposal):
    candidates = _resolve_base_device_candidates(safe_context, proposal)
    if not candidates:
        return candidates
    narrowed = _apply_room_narrowing(safe_context, candidates)
    return _restrict_by_explicit_user_request_device_ids(safe_context, narrowed)


def _resolve_base_device_candidates(safe_context, proposal):
    """Elect identity candidates for the single-device resolver.

    An exact configured device id literally present in the user request is
    authoritative evidence and must seed the candidate set even when the
    model proposal omits or contradicts device identity. Multiple explicit
    ids, or a proposed id that contradicts the explicit id, fail closed.
    Generic referenced text still flows through the legacy generic chain so
    room narrowing and the explicit-id restriction gate reconcile it.
    """
    user_request = safe_context.user_request
    id_candidates = _resolve_device_id_candidates(
        safe_context,
        proposal.referenced_device_id,
    )
    text_candidates = _resolve_device_text_candidates(
        safe_context,
        proposal.referenced_device_text,
    )
    id_grounded = _device_id_is_grounded(user_request, proposal.referenced_device_id)
    text_grounded = _device_text_is_grounded(user_request, proposal.referenced_device_text)
    explicit_ids = _exact_user_request_device_ids(safe_context)
    request_tokens = _normalized_tokens(user_request)
    display_mentions = _display_phrase_present_device_ids(
        safe_context,
        request_tokens,
    )

    if len(set(explicit_ids) | display_mentions) > 1:
        return ()
    explicit_id = explicit_ids[0] if explicit_ids else None

    if explicit_id and proposal.referenced_device_id and proposal.referenced_device_id != explicit_id:
        return ()

    if proposal.referenced_device_id and len(id_candidates) == 1 and id_grounded:
        if proposal.referenced_device_text:
            if not text_grounded:
                return id_candidates
            if len(text_candidates) == 1:
                if id_candidates[0].device_id == text_candidates[0].device_id:
                    return id_candidates
                return ()
            if (
                _referenced_text_is_exact_device_id_literal(
                    user_request,
                    id_candidates[0].device_id,
                    proposal.referenced_device_text,
                )
                and not _has_conflicting_power_switch_intents(user_request)
            ):
                return id_candidates
            return ()
        return id_candidates
    exact_candidates = _resolve_exact_display_name_candidates(safe_context, proposal)
    if exact_candidates:
        if explicit_id and {
            device.device_id for device in exact_candidates
        } != {explicit_id}:
            return ()
        return exact_candidates
    if proposal.referenced_device_id:
        if proposal.referenced_device_text and text_grounded:
            return text_candidates
        return ()
    if text_candidates and text_grounded:
        return text_candidates
    if explicit_id:
        return _resolve_device_id_candidates(safe_context, explicit_id)
    return ()


def _resolve_exact_display_name_candidates(safe_context, proposal):
    """Resolve displays that are complete, proven device references.

    Exact display-name identity is claimed only when the deterministic
    resolver can prove from user_request itself that a configured display
    name is the complete device reference, AND the model-proposed referenced
    text is a full normalized match for that display name. The model span
    never defines entity boundaries; it is only a consistency signal. Full
    equality is required: case- and accent-insensitive, token-boundary safe,
    with no fuzzy matching, no synonym expansion, and no prefix/substring or
    suffix/numeric acceptance. Generic class terms such as "lamp" are never
    exact identities, and requests naming more than one configured display
    (for example "compare Desk Lamp with Floor Lamp") cannot seize a single
    device. Grounded device ids already return earlier with higher
    precedence.
    """
    referenced_text = proposal.referenced_device_text
    referenced_norm = _normalize(referenced_text)
    if not referenced_norm:
        return ()
    if _referenced_text_is_generic(referenced_text, safe_context):
        return ()
    request_tokens = _normalized_tokens(safe_context.user_request)
    if not request_tokens:
        return ()
    boundary_ids = _display_entity_boundary_device_ids(safe_context, request_tokens)
    if not boundary_ids:
        return ()
    matches = [
        device
        for device in safe_context.devices
        if not _display_name_is_generic_class_term(device)
        and _normalize(device.display_name) == referenced_norm
        and device.device_id in boundary_ids
    ]
    if not matches:
        return ()
    if len(_display_phrase_present_device_ids(safe_context, request_tokens)) > 1:
        return ()
    return tuple(sorted(matches, key=lambda device: device.device_id))


def _display_entity_boundary_device_ids(safe_context, request_tokens):
    """Configured displays that occur in the request with a clean boundary.

    A display phrase is a complete device reference only if no occurrence is
    immediately preceded or followed by a token that plausibly continues the
    same device noun phrase. The structural acceptance sets cover only the
    small command grammar that clearly begins a separate clause or location
    (prepositions, articles, determiners, command verbs). Generic connectors
    such as "and", "or", "with", or "but" are never boundary proof by
    themselves because they do not prove the user finished naming the
    device. Any extended occurrence rejects exact identity, so a longer
    user-authored entity such as "Desk Lamp Backup", "Desk Lamp 2", "Fake
    Desk Lamp", or "Desk Lamp and backup" can never collapse into the
    shorter display "Desk Lamp". This is structural, not a suffix list, and
    it fails closed.
    """
    boundary_ids = set()
    for device in safe_context.devices:
        if _display_name_is_generic_class_term(device):
            continue
        phrase = tuple(_normalize(device.display_name).split())
        if not phrase:
            continue
        if not _has_token_phrase(request_tokens, phrase):
            continue
        if not _phrase_has_clean_boundary(request_tokens, phrase):
            continue
        boundary_ids.add(device.device_id)
    return boundary_ids


def _phrase_has_clean_boundary(tokens, phrase):
    size = len(phrase)
    for index in _phrase_start_indexes(tokens, phrase):
        before_ok = index == 0 or tokens[index - 1] in ENTITY_BOUNDARY_BEFORE_TERMS
        after_ok = (
            index + size == len(tokens)
            or tokens[index + size] in ENTITY_BOUNDARY_AFTER_TERMS
        )
        if not (before_ok and after_ok):
            return False
    return True


def _display_phrase_present_device_ids(safe_context, request_tokens):
    present = set()
    for device in safe_context.devices:
        if _display_name_is_generic_class_term(device):
            continue
        phrase = tuple(_normalize(device.display_name).split())
        if phrase and _has_token_phrase(request_tokens, phrase):
            present.add(device.device_id)
    return present


def _referenced_text_is_generic(device_text, safe_context):
    tokens = _normalized_tokens(device_text)
    if not tokens:
        return False
    return all(token in _generic_device_text_terms(safe_context) for token in tokens)


def _generic_device_text_terms(safe_context):
    terms = set()
    for synonyms in DEVICE_TEXT_SYNONYMS.values():
        terms.update(synonyms)
    for device in safe_context.devices:
        terms.add(_normalize(device.device_type))
    return terms


def _display_name_is_generic_class_term(device):
    display_name = _normalize(device.display_name)
    device_type = _normalize(device.device_type)
    if not display_name:
        return False
    generic_class_terms = {device_type}
    generic_class_terms.update(DEVICE_TEXT_SYNONYMS.get(device_type, ()))
    return display_name in generic_class_terms


def _resolve_device_id_candidates(safe_context, device_id):
    if device_id:
        return tuple(
            device
            for device in safe_context.devices
            if device.device_id == device_id
        )
    return ()


def _resolve_device_text_candidates(safe_context, device_text):
    if not _referenced_text_is_generic(device_text, safe_context):
        return ()
    text_terms = _semantic_terms(device_text)
    if not text_terms:
        return ()
    candidates = [
        device
        for device in safe_context.devices
        if text_terms
        & (
            _semantic_terms(device.device_id)
            | _semantic_terms(device.display_name)
            | _semantic_terms(device.device_type)
        )
    ]
    return tuple(sorted(candidates, key=lambda device: device.device_id))


def _apply_room_narrowing(safe_context, candidates):
    mentioned = _mentioned_room_labels(safe_context)
    if len(mentioned) > 1:
        return ()
    if len(mentioned) == 1:
        room = next(iter(mentioned))
        return tuple(
            device
            for device in candidates
            if device.room and _normalize(device.room) == room
        )
    if _request_has_unmatched_location(safe_context):
        return ()
    return candidates


def _restrict_by_explicit_user_request_device_ids(safe_context, candidates):
    """Fail closed when user-request device ids conflict with candidates.

    An exact configured device id literally present in the user request is
    deterministic evidence that no generic, display-name, or room path may
    silently override. Multiple explicit ids are inherently ambiguous for
    the single-device resolver and always clarify. A single explicit id may
    keep the proposed election only when every elected candidate is that
    same device; otherwise the selection is unsafe and clarifies.
    """
    explicit = _exact_user_request_device_ids(safe_context)
    if not explicit:
        return candidates
    if len(explicit) > 1:
        return ()
    explicit_id = explicit[0]
    candidate_ids = {device.device_id for device in candidates}
    if candidate_ids == {explicit_id}:
        return candidates
    return ()


def _exact_user_request_device_ids(safe_context):
    """Configured device ids literally present in the user request.

    Only exact token-safe equality is accepted. Substring, prefix, suffix,
    numeric-normalized, and edit-distance variants never count as mentions.
    Token-edge punctuation already handled by the shared tokenizer (for
    example ",", "(", quotes) does not hide a mention, while embedded forms
    such as "lamp_20", "lamp_2_backup", or "lamp_2-backup" remain distinct
    tokens and never match a configured "lamp_2".
    """
    request_tokens = _normalized_tokens(safe_context.user_request)
    if not request_tokens:
        return ()
    explicit = []
    for device in safe_context.devices:
        phrase = tuple(_normalize(device.device_id).split())
        if phrase and _has_token_phrase(request_tokens, phrase):
            explicit.append(device.device_id)
    return tuple(dict.fromkeys(explicit))


def _request_has_unmatched_location(safe_context):
    """Detect location-like language that mentions no configured room.

    A request such as "enciende la luz del garage" with no configured room
    named "garage" must never fall through to the only generic light. This
    is a small fail-closed grammar over locative preposition phrases in the
    current command language (Spanish/English). Arbitrary unknown room
    language outside this pattern cannot be recognized deterministically
    without heuristic NLP; unmatched locative phrasing always clarifies and
    never executes.
    """
    tokens = _normalized_tokens(safe_context.user_request)
    if len(tokens) < 2:
        return False
    anchors = set()
    for device in safe_context.devices:
        anchors.update(_semantic_terms(device.device_id))
        anchors.update(_semantic_terms(device.display_name))
        anchors.update(_semantic_terms(device.device_type))
    for role_term in DEVICE_ROLE_ANCHOR_TERMS:
        anchors.update(_semantic_terms(role_term))
    for index, token in enumerate(tokens):
        if token not in LOCATIVE_PREPOSITIONS:
            continue
        scanned = index + 1
        while scanned < len(tokens) and tokens[scanned] in LOCATIVE_ARTICLES:
            scanned += 1
        if scanned >= len(tokens):
            continue
        if tokens[scanned] not in anchors:
            return True
    return False


def _mentioned_room_labels(safe_context):
    rooms = {device.room for device in safe_context.devices if device.room}
    request_tokens = _normalized_tokens(safe_context.user_request)
    mentioned = set()
    for room in rooms:
        room_terms = tuple(_normalize(room).split())
        if _has_token_phrase(request_tokens, room_terms):
            mentioned.add(_normalize(room))
    return mentioned


def _find_capability(device, capability_hint):
    if not capability_hint:
        return None
    for capability in device.capabilities:
        if capability.name == capability_hint:
            return capability
    return None


def _missing_required_arguments(arguments, capability):
    missing = []
    for descriptor in capability.parameters:
        parameter = dict(descriptor)
        name = parameter.get("name")
        if parameter.get("required") is True and name not in arguments:
            missing.append(name)
    return sorted(missing)


def _arguments_as_dict(raw_arguments):
    arguments = {}
    for key, value in raw_arguments:
        if key in arguments:
            raise ValueError("duplicate raw argument keys are not allowed")
        arguments[key] = value
    return arguments


def _ungrounded_arguments(user_request, arguments, capability):
    required_names = {
        dict(descriptor).get("name")
        for descriptor in capability.parameters
        if dict(descriptor).get("required") is True
    }
    missing = []
    for name in sorted(required_names):
        if name not in arguments:
            missing.append(name)
            continue
        if not _argument_is_grounded(
            user_request,
            capability.name,
            name,
            arguments[name],
        ):
            missing.append(name)
    return missing


def _argument_is_grounded(user_request, capability_name, key, value):
    key_norm = _normalize(key)
    value_norm = _normalize(value)
    if not key_norm or not value_norm:
        return False
    if _has_exact_raw_token(user_request, f"{key}={value}"):
        return True
    if _has_adjacent_raw_tokens(user_request, key, value):
        return True
    if _has_exact_token(user_request, f"{key_norm}={value_norm}"):
        return True
    if _has_adjacent_tokens(user_request, key_norm, value_norm):
        return True
    if capability_name == "power.switch" and key_norm == "state":
        if value_norm in TRUE_VALUES:
            return _has_imperative_power_switch(user_request, target_state=True)
        if value_norm in FALSE_VALUES:
            return _has_imperative_power_switch(user_request, target_state=False)
    return False


def _capability_hint_is_grounded(user_request, capability_hint):
    capability = _normalize(capability_hint)
    if not capability:
        return False
    request = _normalize(user_request)
    if capability in request:
        return True
    request_terms = _semantic_terms(user_request)
    if capability == "status.read":
        return bool(request_terms & READ_STATUS_TERMS)
    if capability == "power.switch":
        return _has_imperative_power_switch(user_request, target_state=None)
    return False


def _execute_plan(command, device_id, capability_name, action_kind):
    requires_confirmation = action_kind != ACTION_KIND_READ
    flags = ("read_only",) if action_kind == ACTION_KIND_READ else (
        "device_mutation",
        "requires_confirmation",
    )
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": PLAN_KIND_EXECUTE,
        "steps": [
            {
                "index": 0,
                "canonical_command_text": command,
                "safe_description": f"Prepare {capability_name} on {device_id}.",
                "target_device_id": device_id,
                "capability_name": capability_name,
                "action_kind": action_kind,
                "requires_confirmation": requires_confirmation,
                "policy_flags": list(flags),
            }
        ],
        "safe_summary": "Prepared a deterministic device plan.",
        "clarification": None,
        "refusal": None,
        "confirmation_required": requires_confirmation,
        "policy_flags": list(flags),
    }


def _clarify_plan(reason_code, question, missing_fields, candidate_options):
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": PLAN_KIND_CLARIFY,
        "steps": [],
        "safe_summary": "More information is needed.",
        "clarification": {
            "question": question,
            "reason_code": reason_code,
            "missing_fields": list(missing_fields),
            "candidate_options": list(candidate_options),
        },
        "refusal": None,
        "confirmation_required": False,
        "policy_flags": [],
    }


def _refuse_plan(reason_code, message):
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "kind": PLAN_KIND_REFUSE,
        "steps": [],
        "safe_summary": "The request was refused.",
        "clarification": None,
        "refusal": {
            "safe_message": message,
            "reason_code": reason_code,
        },
        "confirmation_required": False,
        "policy_flags": [],
    }


def _is_destructive_request(user_request):
    if DESTRUCTIVE_PATTERN.search(user_request):
        return True
    terms = {_normalize(term) for term in user_request.split()}
    return bool(terms & DESTRUCTIVE_TERMS)


def _normalize(value):
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^\w.=-]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.strip().casefold().split())


def _device_id_is_grounded(user_request, device_id):
    device = _normalize(device_id)
    if not device:
        return False
    return _has_exact_token(user_request, device)


def _referenced_text_is_exact_device_id_literal(user_request, device_id, referenced_text):
    """True when referenced text is the literal of a grounded device id.

    The model already grounded the device id in the user request, and the
    referenced text normalizes to that exact literal. Only literal equality
    is accepted: "lamp_2" or punctuation-edged "lamp_2." confirm the model
    span, while "lamp_20", "lamp_2_backup", or "lamp_2-b" never do.
    """
    device_normalized = _normalize(device_id)
    referenced_normalized = _normalize(referenced_text)
    if not device_normalized or not referenced_normalized:
        return False
    if referenced_normalized.strip(".=-") != device_normalized.strip(".=-"):
        return False
    return _device_id_is_grounded(user_request, device_id)


def _has_conflicting_power_switch_intents(user_request):
    """True when the request grounds both a power-on and a power-off intent.

    A request such as "Turn on lamp_1 and apagar it" names conflicting
    targets for the same device; a single canonical command cannot represent
    both, so exact-ID literal confirmation must fail closed in that case.
    """
    return _has_imperative_power_switch(
        user_request, target_state=True
    ) and _has_imperative_power_switch(user_request, target_state=False)


def _device_text_is_grounded(user_request, device_text):
    request_terms = _semantic_terms(user_request)
    text_terms = _semantic_terms(device_text)
    return bool(text_terms and request_terms & text_terms)


def _semantic_terms(value):
    tokens = _normalized_tokens(value)
    if not tokens:
        return set()
    normalized = " ".join(tokens)
    terms = set(tokens)
    terms = {term for term in terms if term}
    if normalized:
        terms.add(normalized)
    expanded = set(terms)
    for term in terms:
        expanded.update(DEVICE_TEXT_SYNONYMS.get(term, ()))
    return expanded


def _has_exact_token(value, token):
    return _normalize(token) in _normalized_tokens(value)


def _has_exact_raw_token(value, token):
    token = str(token).strip().casefold()
    if not token:
        return False
    return token in _raw_tokens(value)


def _has_adjacent_raw_tokens(value, first, second):
    tokens = _raw_tokens(value)
    first = str(first).strip().casefold()
    second = str(second).strip().casefold()
    return any(
        left == first and right == second
        for left, right in zip(tokens, tokens[1:])
    )


def _has_adjacent_tokens(value, first, second):
    tokens = _normalized_tokens(value)
    first = _normalize(first)
    second = _normalize(second)
    return any(
        left == first and right == second
        for left, right in zip(tokens, tokens[1:])
    )


def _normalized_tokens(value):
    normalized = _normalize(value)
    if not normalized:
        return ()
    return tuple(
        token.strip(".=-")
        for token in normalized.split()
        if token.strip(".=-")
    )


def _raw_tokens(value):
    return tuple(
        token.strip(".,;:!?¿¡()[]{}\"'").casefold()
        for token in str(value).split()
        if token.strip(".,;:!?¿¡()[]{}\"'")
    )


def _has_imperative_power_switch(user_request, target_state):
    if _looks_like_question(user_request) or _has_negated_power_switch(user_request):
        return False
    tokens = _normalized_tokens(user_request)
    terms = set(tokens)
    if target_state is True:
        return bool(terms & POWER_SWITCH_ON_VERBS) or any(
            _has_token_phrase(tokens, phrase) for phrase in POWER_SWITCH_ON_PHRASES
        )
    if target_state is False:
        return bool(terms & POWER_SWITCH_OFF_VERBS) or any(
            _has_token_phrase(tokens, phrase) for phrase in POWER_SWITCH_OFF_PHRASES
        )
    return (
        bool(terms & (POWER_SWITCH_ON_VERBS | POWER_SWITCH_OFF_VERBS))
        or any(_has_token_phrase(tokens, phrase) for phrase in POWER_SWITCH_ON_PHRASES)
        or any(_has_token_phrase(tokens, phrase) for phrase in POWER_SWITCH_OFF_PHRASES)
    )


def _looks_like_question(user_request):
    text = str(user_request)
    if "?" in text or "¿" in text:
        return True
    tokens = _normalized_tokens(user_request)
    return bool(tokens and tokens[0] in QUESTION_TERMS)


def _has_negated_power_switch(user_request):
    tokens = _normalized_tokens(user_request)
    for index, token in enumerate(tokens):
        if token in POWER_SWITCH_ON_VERBS or token in POWER_SWITCH_OFF_VERBS:
            window = tokens[max(0, index - 3):index]
            if set(window) & NEGATION_TERMS:
                return True
    for phrase in POWER_SWITCH_ON_PHRASES | POWER_SWITCH_OFF_PHRASES:
        for index in _phrase_start_indexes(tokens, phrase):
            window = tokens[max(0, index - 3):index]
            if set(window) & NEGATION_TERMS:
                return True
    return False


def _has_token_phrase(tokens, phrase):
    return bool(_phrase_start_indexes(tokens, phrase))


def _phrase_start_indexes(tokens, phrase):
    size = len(phrase)
    return tuple(
        index
        for index in range(0, len(tokens) - size + 1)
        if tuple(tokens[index:index + size]) == tuple(phrase)
    )


__all__ = [
    "DeterministicUnderstandingResolver",
]
