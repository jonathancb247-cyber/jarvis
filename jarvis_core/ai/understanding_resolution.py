"""Deterministic resolution for local AI understanding proposals."""

import re

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
        capability = _find_capability(device, proposal.capability_hint)
        if capability is None:
            return _clarify_plan(
                "unsupported_request",
                "That capability is not available for the resolved device.",
                ("capability_name",),
                tuple(capability.name for capability in device.capabilities[:5]),
            )

        arguments = dict(proposal.raw_arguments)
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
    id_candidates = _resolve_device_id_candidates(
        safe_context,
        proposal.referenced_device_id,
    )
    text_candidates = _resolve_device_text_candidates(
        safe_context,
        proposal.referenced_device_text,
    )

    if proposal.referenced_device_id and proposal.referenced_device_text:
        if len(id_candidates) != 1 or len(text_candidates) != 1:
            return ()
        if id_candidates[0].device_id != text_candidates[0].device_id:
            return ()
        return id_candidates
    if proposal.referenced_device_id:
        return id_candidates
    return text_candidates


def _resolve_device_id_candidates(safe_context, device_id):
    if device_id:
        return tuple(
            device
            for device in safe_context.devices
            if device.device_id == device_id
        )
    return ()


def _resolve_device_text_candidates(safe_context, device_text):
    text = _normalize(device_text)
    if not text:
        return ()
    candidates = [
        device
        for device in safe_context.devices
        if text
        in {
            _normalize(device.device_id),
            _normalize(device.display_name),
            _normalize(device.device_type),
        }
    ]
    return tuple(sorted(candidates, key=lambda device: device.device_id))


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
    return str(value).strip().casefold()


__all__ = [
    "DeterministicUnderstandingResolver",
]
