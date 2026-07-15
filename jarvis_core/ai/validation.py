"""Validation and normalization for AI Adapter plans."""

import re

from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
    ACTION_KIND_READ,
    ACTION_KIND_UNKNOWN,
    AI_PLAN_REJECTED,
    AI_RESPONSE_INVALID,
    MAX_COMMAND_LENGTH,
    MAX_PLAN_STEPS,
    MAX_SAFE_TEXT_LENGTH,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
    PLAN_SCHEMA_VERSION,
    AIActionPlan,
    AIActionStep,
    AIClarification,
    AIRefusal,
)
from jarvis_core.planner import (
    APPLY_OPERATION,
    DEVICE_CATALOG_COMMAND,
    DEVICE_EXECUTE_COMMAND,
    READ_OPERATION,
)


PLAN_FIELDS = {
    "schema_version",
    "kind",
    "steps",
    "safe_summary",
    "clarification",
    "refusal",
    "confirmation_required",
    "policy_flags",
}
STEP_FIELDS = {
    "index",
    "canonical_command_text",
    "safe_description",
    "target_device_id",
    "capability_name",
    "action_kind",
    "requires_confirmation",
    "policy_flags",
}
CLARIFICATION_FIELDS = {
    "question",
    "reason_code",
    "missing_fields",
    "candidate_options",
}
REFUSAL_FIELDS = {"safe_message", "reason_code"}

URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
WINDOWS_PATH_PATTERN = re.compile(r"[A-Za-z]:\\|\\\\")
UNIX_PATH_PATTERN = re.compile(r"(^|\\s)/(?!/)")
PYTHON_PATTERN = re.compile(r"\b(import|lambda|exec|eval|python)\b|__", re.IGNORECASE)
BACKGROUND_PATTERN = re.compile(r"\b(schtasks|start\s+/b|nohup)\b|&", re.IGNORECASE)


class AIValidationError(Exception):
    """Safe adapter validation error."""

    def __init__(self, code, reason="invalid AI plan"):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def normalize_plan(payload):
    if not isinstance(payload, dict):
        raise AIValidationError(AI_RESPONSE_INVALID, "plan_normalization_failed")
    _reject_unknown(payload, PLAN_FIELDS)
    try:
        steps = tuple(normalize_step(item) for item in payload.get("steps", []))
        clarification = _normalize_clarification(payload.get("clarification"))
        refusal = _normalize_refusal(payload.get("refusal"))
        return AIActionPlan(
            schema_version=payload["schema_version"],
            kind=payload["kind"],
            steps=steps,
            safe_summary=payload.get("safe_summary", ""),
            clarification=clarification,
            refusal=refusal,
            confirmation_required=bool(payload.get("confirmation_required", False)),
            policy_flags=tuple(payload.get("policy_flags", [])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AIValidationError(AI_RESPONSE_INVALID, "plan_normalization_failed") from error


def normalize_step(payload):
    if not isinstance(payload, dict):
        raise AIValidationError(AI_RESPONSE_INVALID, "plan_normalization_failed")
    _reject_unknown(payload, STEP_FIELDS)
    try:
        return AIActionStep(
            index=payload["index"],
            canonical_command_text=payload["canonical_command_text"],
            safe_description=payload["safe_description"],
            target_device_id=payload.get("target_device_id"),
            capability_name=payload.get("capability_name"),
            action_kind=payload.get("action_kind", ACTION_KIND_UNKNOWN),
            requires_confirmation=bool(payload.get("requires_confirmation", False)),
            policy_flags=tuple(payload.get("policy_flags", [])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AIValidationError(AI_RESPONSE_INVALID, "plan_normalization_failed") from error


def validate_plan_shape(plan):
    if plan.schema_version != PLAN_SCHEMA_VERSION:
        raise AIValidationError(AI_RESPONSE_INVALID)
    if plan.kind == PLAN_KIND_EXECUTE:
        if not 1 <= len(plan.steps) <= MAX_PLAN_STEPS:
            raise AIValidationError(AI_PLAN_REJECTED, "contract_validation_failed")
        expected = list(range(len(plan.steps)))
        actual = [step.index for step in plan.steps]
        if actual != expected:
            raise AIValidationError(AI_PLAN_REJECTED, "contract_validation_failed")
    return plan


def validate_command_text_safety(command_text):
    if not isinstance(command_text, str) or not command_text.strip():
        raise AIValidationError(AI_PLAN_REJECTED, "command_safety_validation_failed")
    if len(command_text) > MAX_COMMAND_LENGTH:
        raise AIValidationError(AI_PLAN_REJECTED, "command_safety_validation_failed")
    if "\n" in command_text or "\r" in command_text:
        raise AIValidationError(AI_PLAN_REJECTED, "command_safety_validation_failed")
    forbidden_tokens = [";", "&&", "||", "|", ">", "<", "#", "`", "$("]
    if any(token in command_text for token in forbidden_tokens):
        raise AIValidationError(AI_PLAN_REJECTED, "command_safety_validation_failed")
    if URL_PATTERN.search(command_text):
        raise AIValidationError(AI_PLAN_REJECTED, "command_safety_validation_failed")
    if WINDOWS_PATH_PATTERN.search(command_text) or UNIX_PATH_PATTERN.search(command_text):
        raise AIValidationError(AI_PLAN_REJECTED, "command_safety_validation_failed")
    if PYTHON_PATTERN.search(command_text) or BACKGROUND_PATTERN.search(command_text):
        raise AIValidationError(AI_PLAN_REJECTED, "command_safety_validation_failed")
    return command_text


def validate_with_planner(planner, command_text):
    command = planner.plan(command_text, source="ai.adapter")
    if command.name == "unknown":
        raise AIValidationError(AI_PLAN_REJECTED, "planner_validation_failed")
    return command


def validate_against_context(step, command, safe_context):
    if command.name == DEVICE_EXECUTE_COMMAND:
        return _validate_device_execute(step, command, safe_context)
    if command.name == DEVICE_CATALOG_COMMAND:
        return command
    raise AIValidationError(AI_PLAN_REJECTED, "semantic_validation_failed")


def classify_command(command, safe_context):
    if command.name == DEVICE_CATALOG_COMMAND:
        return ACTION_KIND_READ
    if command.name != DEVICE_EXECUTE_COMMAND:
        return ACTION_KIND_UNKNOWN
    operation = command.args.get("operation")
    if operation == APPLY_OPERATION:
        return ACTION_KIND_MUTATE
    if operation == READ_OPERATION:
        device = _find_device(safe_context, command.args.get("device_id"))
        capability = _find_capability(device, command.args.get("capability"))
        if capability is not None and capability.kind == "reading":
            return ACTION_KIND_READ
    return ACTION_KIND_UNKNOWN


def recompute_step(step, action_kind):
    requires_confirmation = action_kind != ACTION_KIND_READ
    flags = []
    if action_kind == ACTION_KIND_READ:
        flags.append("read_only")
    elif action_kind == ACTION_KIND_MUTATE:
        flags.extend(["device_mutation", "requires_confirmation"])
    else:
        flags.extend(["unknown_action", "requires_confirmation"])
    return AIActionStep(
        index=step.index,
        canonical_command_text=step.canonical_command_text,
        safe_description=step.safe_description,
        target_device_id=step.target_device_id,
        capability_name=step.capability_name,
        action_kind=action_kind,
        requires_confirmation=requires_confirmation,
        policy_flags=tuple(flags),
    )


def recompute_plan(plan, steps):
    confirmation_required = any(step.requires_confirmation for step in steps)
    flags = []
    if confirmation_required:
        flags.append("requires_confirmation")
    if len(steps) > 1:
        flags.append("multi_step")
    return AIActionPlan(
        schema_version=plan.schema_version,
        kind=plan.kind,
        steps=tuple(steps),
        safe_summary=plan.safe_summary,
        clarification=plan.clarification,
        refusal=plan.refusal,
        confirmation_required=confirmation_required,
        policy_flags=tuple(flags),
    )


def _validate_device_execute(step, command, safe_context):
    device_id = command.args.get("device_id")
    capability_name = command.args.get("capability")
    operation = command.args.get("operation")
    parameters = command.args.get("parameters", {})
    device = _find_device(safe_context, device_id)
    if device is None:
        raise AIValidationError(AI_PLAN_REJECTED, "semantic_validation_failed")
    capability = _find_capability(device, capability_name)
    if capability is None:
        raise AIValidationError(AI_PLAN_REJECTED, "semantic_validation_failed")
    if step.target_device_id is not None and step.target_device_id != device_id:
        raise AIValidationError(AI_PLAN_REJECTED, "semantic_validation_failed")
    if step.capability_name is not None and step.capability_name != capability_name:
        raise AIValidationError(AI_PLAN_REJECTED, "semantic_validation_failed")
    if operation == READ_OPERATION and capability.kind != "reading":
        raise AIValidationError(AI_PLAN_REJECTED, "semantic_validation_failed")
    if operation == APPLY_OPERATION and capability.kind != "action":
        raise AIValidationError(AI_PLAN_REJECTED, "semantic_validation_failed")
    if operation == APPLY_OPERATION:
        _validate_required_parameters(parameters, capability)
    return command


def _validate_required_parameters(parameters, capability):
    required = {
        dict(descriptor).get("name")
        for descriptor in capability.parameters
        if dict(descriptor).get("required") is True
    }
    missing = [name for name in required if name not in parameters]
    if missing:
        raise AIValidationError(AI_PLAN_REJECTED, "semantic_validation_failed")


def _find_device(safe_context, device_id):
    for device in safe_context.devices:
        if device.device_id == device_id:
            return device
    return None


def _find_capability(device, capability_name):
    if device is None:
        return None
    for capability in device.capabilities:
        if capability.name == capability_name:
            return capability
    return None


def _normalize_clarification(payload):
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise AIValidationError(AI_RESPONSE_INVALID, "plan_normalization_failed")
    _reject_unknown(payload, CLARIFICATION_FIELDS)
    return AIClarification(
        question=payload["question"],
        reason_code=payload["reason_code"],
        missing_fields=tuple(payload.get("missing_fields", [])),
        candidate_options=tuple(payload.get("candidate_options", [])),
    )


def _normalize_refusal(payload):
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise AIValidationError(AI_RESPONSE_INVALID, "plan_normalization_failed")
    _reject_unknown(payload, REFUSAL_FIELDS)
    return AIRefusal(
        safe_message=payload["safe_message"],
        reason_code=payload["reason_code"],
    )


def _reject_unknown(payload, allowed):
    unknown = set(payload) - allowed
    if unknown:
        raise AIValidationError(AI_RESPONSE_INVALID, "plan_normalization_failed")
