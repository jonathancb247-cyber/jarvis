"""Safe local execution gate for validated local understanding decisions.

This module is the only approved boundary through which a non-executing
``LocalUnderstandingDecision`` may reach the existing deterministic Runtime.
It never trusts the AI-produced plan as an authority: it re-derives the
canonical command through the existing Planner and applies a strict allowlist
before anything reaches ``Runtime.execute``.

Execution is split into ``prepare`` and ``confirm`` so that every v1
``power.switch`` mutation is subject to mandatory explicit confirmation:

- ``prepare(decision)`` validates the decision, derives the command, verifies
  current device/capability availability, binds a normalized plan digest in
  the existing ``AIConfirmationStore``, and never calls Runtime.
- ``confirm(confirmation_id, plan_digest)`` re-validates the exact stored plan
  (TOCTOU safety), re-checks device/capability availability, and only then
  calls ``Runtime.execute`` exactly once. Confirmations are single-use.
- ``cancel(confirmation_id)`` invalidates a pending confirmation and never
  calls Runtime.

Design rules:

- Only ``EXECUTABLE_CANDIDATE`` decisions are eligible; clarify, refuse,
  unavailable and failed decisions are rejected before any confirmation.
- Incoming ``decision.confirmation_required`` is ignored: every v1
  ``power.switch`` mutation requires confirmation regardless.
- Only single-step execute plans are allowed; multi-step plans are rejected.
- The canonical command text is re-validated for safety and re-planned with
  the existing Planner; nothing trusts stored plan fields by themselves.
- The strict v1 allowlist accepts exactly ``power.switch`` with
  ``{"state": "true"}`` or ``{"state": "false"}``. The gate never broadens
  values (``on``/``off`` are rejected) and rejects any unexpected parameter
  form.
- One confirmation mechanism only: the existing ``AIConfirmationStore`` and
  ``plan_digest`` are reused; no second mechanism is created.

Result semantics are explicit and never conflated:

- ``commands_executed=False``: confirmation_required, rejected, cancelled, or
  failed before Runtime invocation.
- ``commands_executed=True``: Runtime was invoked. A device/capability failure
  is ``execution_failed`` with bounded ``CapabilityResult`` semantics.
- Raw exceptions and ``DriverResult`` internals are never exposed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from jarvis_core.ai.confirmation import AIConfirmationStore
from jarvis_core.ai.contracts import (
    AI_CONFIRMATION_REQUIRED,
    AI_EXECUTION_NOT_CONFIRMED,
    PLAN_KIND_EXECUTE,
)
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    LocalUnderstandingDecision,
)
from jarvis_core.ai.validation import AIValidationError, validate_command_text_safety
from jarvis_core.devices import DeviceCapability
from jarvis_core.domain import CapabilityResult
from jarvis_core.planner import (
    APPLY_OPERATION,
    DEVICE_EXECUTE_COMMAND,
    Planner,
)

if TYPE_CHECKING:
    from jarvis_core.runtime import Runtime

EXECUTION_GATE_SOURCE = "ai.execution_gate"

ALLOWED_CAPABILITIES = frozenset({"power.switch"})
ALLOWED_POWER_SWITCH_STATES = frozenset({"true", "false"})
POWER_SWITCH_ARGUMENT = "state"
POWER_SWITCH_PARAMETER_SETS = frozenset(
    {
        ("state", "true"),
        ("state", "false"),
    }
)

GATE_STATUS_CONFIRMATION_REQUIRED = "confirmation_required"
GATE_STATUS_EXECUTED = "executed"
GATE_STATUS_EXECUTION_FAILED = "execution_failed"
GATE_STATUS_REJECTED = "rejected"
GATE_STATUS_CANCELLED = "cancelled"

GATE_STATUSES = frozenset(
    {
        GATE_STATUS_CONFIRMATION_REQUIRED,
        GATE_STATUS_EXECUTED,
        GATE_STATUS_EXECUTION_FAILED,
        GATE_STATUS_REJECTED,
        GATE_STATUS_CANCELLED,
    }
)

REJECT_UNSUPPORTED_DECISION = "unsupported_decision"
REJECT_DECISION_CLAIMS_EXECUTION = "decision_claims_execution"
REJECT_DECISION_NOT_EXECUTABLE = "decision_not_executable"
REJECT_MISSING_EXECUTE_PLAN = "missing_execute_plan"
REJECT_MULTI_STEP_PLAN = "multi_step_plan"
REJECT_INVALID_COMMAND = "invalid_command"
REJECT_UNSUPPORTED_CAPABILITY = "unsupported_capability"
REJECT_INVALID_ARGUMENTS = "invalid_arguments"
REJECT_DEVICE_UNAVAILABLE = "device_unavailable"
REJECT_CAPABILITY_UNAVAILABLE = "capability_unavailable"
REJECT_CONFIRMATION_NOT_FOUND = "confirmation_not_found"
REJECT_CONFIRMATION_DIGEST_MISMATCH = "confirmation_digest_mismatch"

REJECT_REASONS = frozenset(
    {
        REJECT_UNSUPPORTED_DECISION,
        REJECT_DECISION_CLAIMS_EXECUTION,
        REJECT_DECISION_NOT_EXECUTABLE,
        REJECT_MISSING_EXECUTE_PLAN,
        REJECT_MULTI_STEP_PLAN,
        REJECT_INVALID_COMMAND,
        REJECT_UNSUPPORTED_CAPABILITY,
        REJECT_INVALID_ARGUMENTS,
        REJECT_DEVICE_UNAVAILABLE,
        REJECT_CAPABILITY_UNAVAILABLE,
        REJECT_CONFIRMATION_NOT_FOUND,
        REJECT_CONFIRMATION_DIGEST_MISMATCH,
    }
)

CONFIRMATION_REQUIRED_MESSAGE = "Confirmation is required for this device mutation."
REJECT_MESSAGE = "Execution gate rejected the request."
CANCELLED_MESSAGE = "AI plan execution was cancelled."
RUNTIME_EXECUTION_FAILED = "runtime_execution_failed"
RUNTIME_FAILURE_MESSAGE = "Runtime did not complete the command."


@dataclass(frozen=True)
class ExecutionGateResult:
    """Immutable outcome of one gated execution step (prepare/confirm/cancel)."""

    status: str
    success: bool
    commands_executed: bool
    device_id: str | None = None
    capability: str | None = None
    arguments: dict | None = None
    confirmation_id: str | None = None
    plan_digest: str | None = None
    runtime_result: CapabilityResult | None = None
    error: str | None = None
    message: str = ""
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in GATE_STATUSES:
            raise ValueError("gate result status is invalid")
        if not isinstance(self.success, bool):
            raise ValueError("success must be a bool")
        if not isinstance(self.commands_executed, bool):
            raise ValueError("commands_executed must be a bool")
        if not isinstance(self.message, str):
            raise ValueError("message must be a string")
        _optional_label(self.device_id, "device_id")
        _optional_label(self.capability, "capability")
        _optional_label(self.confirmation_id, "confirmation_id")
        _optional_label(self.plan_digest, "plan_digest")
        _optional_label(self.error, "error")
        if self.arguments is not None and not isinstance(self.arguments, dict):
            raise ValueError("arguments must be None or a dict")
        if self.runtime_result is not None and not isinstance(
            self.runtime_result, CapabilityResult
        ):
            raise ValueError("runtime_result must be None or a CapabilityResult")
        if self.reason is not None and self.reason not in REJECT_REASONS:
            raise ValueError("reason is invalid")
        self._validate_status_shape()

    def _validate_status_shape(self) -> None:
        if self.status == GATE_STATUS_CONFIRMATION_REQUIRED:
            if self.commands_executed is not False:
                raise ValueError("confirmation_required cannot claim execution")
            if self.confirmation_id is None or self.plan_digest is None:
                raise ValueError("confirmation_required requires id and digest")
            if self.runtime_result is not None:
                raise ValueError("confirmation_required cannot carry a runtime result")
            if self.success is not False:
                raise ValueError("confirmation_required cannot be successful")
            return
        if self.status == GATE_STATUS_EXECUTED:
            if self.commands_executed is not True:
                raise ValueError("executed requires commands_executed")
            if self.runtime_result is None or not self.runtime_result.success:
                raise ValueError("executed requires a successful runtime result")
            if self.success is not True:
                raise ValueError("executed must be successful")
            if self.error is not None or self.reason is not None:
                raise ValueError("executed cannot carry an error or reason")
            if not self._has_execution_payload():
                raise ValueError(
                    "execution results require id, digest, device, capability and arguments"
                )
            return
        if self.status == GATE_STATUS_EXECUTION_FAILED:
            if self.commands_executed is not True:
                raise ValueError("execution_failed requires commands_executed")
            if self.runtime_result is None or self.runtime_result.success:
                raise ValueError("execution_failed requires a failed runtime result")
            if self.success is not False:
                raise ValueError("execution_failed cannot be successful")
            if self.error != self.runtime_result.error:
                raise ValueError("execution_failed error must match runtime result")
            if self.reason is not None:
                raise ValueError("execution_failed cannot carry a reason")
            if not self._has_execution_payload():
                raise ValueError(
                    "execution results require id, digest, device, capability and arguments"
                )
            return
        if self.status == GATE_STATUS_REJECTED:
            if self.commands_executed is not False:
                raise ValueError("rejected cannot claim execution")
            if self.reason is None or self.reason not in REJECT_REASONS:
                raise ValueError("rejected requires a valid reason")
            if self.runtime_result is not None:
                raise ValueError("rejected cannot carry a runtime result")
            if self.success is not False:
                raise ValueError("rejected cannot be successful")
            if self.confirmation_id is not None or self.plan_digest is not None:
                raise ValueError("rejected cannot carry confirmation fields")
            return
        if self.status == GATE_STATUS_CANCELLED:
            if self.commands_executed is not False:
                raise ValueError("cancelled cannot claim execution")
            if self.runtime_result is not None:
                raise ValueError("cancelled cannot carry a runtime result")
            if self.success is not False:
                raise ValueError("cancelled cannot be successful")
            if self.error != AI_EXECUTION_NOT_CONFIRMED or self.reason is not None:
                raise ValueError("cancelled carries the not-confirmed error only")
            if self.confirmation_id is None or self.plan_digest is None:
                raise ValueError("cancelled requires id and digest")

    def _has_execution_payload(self) -> bool:
        return None not in (
            self.device_id,
            self.capability,
            self.arguments,
            self.confirmation_id,
            self.plan_digest,
        )


class ExecutionGate:
    """Confirmation-gated allowlist boundary before Runtime execution."""

    def __init__(self, runtime, planner=None, confirmation_store=None):
        if not callable(getattr(runtime, "execute", None)):
            raise TypeError("ExecutionGate expects a runtime with execute(command)")
        self.runtime = runtime
        self.planner = planner or Planner()
        if not callable(getattr(self.planner, "plan", None)):
            raise TypeError("ExecutionGate expects a planner with plan(text)")
        self.confirmation_store = confirmation_store or AIConfirmationStore()

    def prepare(self, decision) -> ExecutionGateResult:
        """Validate a decision and bind a pending confirmation; never executes."""
        try:
            plan = self._validated_plan(decision)
            command, device_id, capability, parameters = self._derive(plan)
            self._verify_availability(device_id, capability)
        except _GateRejection as rejection:
            return self._rejected(rejection.reason, error=None)
        state = self.confirmation_store.create(plan)
        return ExecutionGateResult(
            status=GATE_STATUS_CONFIRMATION_REQUIRED,
            success=False,
            commands_executed=False,
            device_id=device_id,
            capability=capability,
            arguments=dict(parameters),
            confirmation_id=state.pending_plan_id,
            plan_digest=state.normalized_plan_digest,
            runtime_result=None,
            error=AI_CONFIRMATION_REQUIRED,
            message=CONFIRMATION_REQUIRED_MESSAGE,
            reason=None,
        )

    def confirm(self, confirmation_id, plan_digest) -> ExecutionGateResult:
        """Re-validate a stored plan and execute it exactly once, or reject."""
        pending = self.confirmation_store.pending
        if pending is None or pending.pending_plan_id != confirmation_id:
            return self._rejected(
                REJECT_CONFIRMATION_NOT_FOUND,
                error=AI_EXECUTION_NOT_CONFIRMED,
            )
        if pending.normalized_plan_digest != plan_digest:
            self.confirmation_store.consume()
            return self._rejected(
                REJECT_CONFIRMATION_DIGEST_MISMATCH,
                error=AI_EXECUTION_NOT_CONFIRMED,
            )

        plan = self.confirmation_store.confirm(
            confirmation_id,
            normalized_plan_digest=plan_digest,
        )
        try:
            command, device_id, capability, parameters = self._derive(plan)
            self._verify_availability(device_id, capability)
        except _GateRejection as rejection:
            self.confirmation_store.consume()
            return self._rejected(rejection.reason, error=None)

        try:
            runtime_result = self.runtime.execute(command)
        except Exception:
            self.confirmation_store.consume()
            return self._execution_failed_after_attempt(
                confirmation_id=confirmation_id,
                plan_digest=plan_digest,
                device_id=device_id,
                capability=capability,
                parameters=parameters,
            )
        self.confirmation_store.consume()
        if not runtime_result.success:
            return ExecutionGateResult(
                status=GATE_STATUS_EXECUTION_FAILED,
                success=False,
                commands_executed=True,
                device_id=device_id,
                capability=capability,
                arguments=dict(parameters),
                confirmation_id=confirmation_id,
                plan_digest=plan_digest,
                runtime_result=runtime_result,
                error=runtime_result.error,
                message=runtime_result.message,
                reason=None,
            )
        return ExecutionGateResult(
            status=GATE_STATUS_EXECUTED,
            success=True,
            commands_executed=True,
            device_id=device_id,
            capability=capability,
            arguments=dict(parameters),
            confirmation_id=confirmation_id,
            plan_digest=plan_digest,
            runtime_result=runtime_result,
            error=None,
            message=runtime_result.message,
            reason=None,
        )

    def cancel(self, confirmation_id) -> ExecutionGateResult:
        """Invalidate a pending confirmation; never calls Runtime."""
        pending = self.confirmation_store.pending
        if pending is None or pending.pending_plan_id != confirmation_id:
            return self._rejected(
                REJECT_CONFIRMATION_NOT_FOUND,
                error=AI_EXECUTION_NOT_CONFIRMED,
            )
        self.confirmation_store.cancel(confirmation_id)
        return ExecutionGateResult(
            status=GATE_STATUS_CANCELLED,
            success=False,
            commands_executed=False,
            device_id=None,
            capability=None,
            arguments=None,
            confirmation_id=confirmation_id,
            plan_digest=pending.normalized_plan_digest,
            runtime_result=None,
            error=AI_EXECUTION_NOT_CONFIRMED,
            message=CANCELLED_MESSAGE,
            reason=None,
        )

    def _validated_plan(self, decision):
        if not isinstance(decision, LocalUnderstandingDecision):
            raise _GateRejection(REJECT_UNSUPPORTED_DECISION)
        if decision.commands_executed is not False:
            raise _GateRejection(REJECT_DECISION_CLAIMS_EXECUTION)
        if decision.status != EXECUTABLE_CANDIDATE:
            raise _GateRejection(REJECT_DECISION_NOT_EXECUTABLE)
        if decision.plan is None or decision.plan.kind != PLAN_KIND_EXECUTE:
            raise _GateRejection(REJECT_DECISION_NOT_EXECUTABLE)
        if not decision.plan.steps:
            raise _GateRejection(REJECT_MISSING_EXECUTE_PLAN)
        return decision.plan

    def _derive(self, plan):
        if plan.kind != PLAN_KIND_EXECUTE or not plan.steps:
            raise _GateRejection(REJECT_MISSING_EXECUTE_PLAN)
        if len(plan.steps) != 1:
            raise _GateRejection(REJECT_MULTI_STEP_PLAN)

        step = plan.steps[0]
        command_text = step.canonical_command_text
        if not command_text or not command_text.strip():
            raise _GateRejection(REJECT_INVALID_COMMAND)
        try:
            validate_command_text_safety(command_text)
        except AIValidationError:
            raise _GateRejection(REJECT_INVALID_COMMAND)

        command = self.planner.plan(command_text, source=EXECUTION_GATE_SOURCE)
        if command.name != DEVICE_EXECUTE_COMMAND:
            raise _GateRejection(REJECT_INVALID_COMMAND)

        args = command.args
        device_id = args.get("device_id")
        capability = args.get("capability")
        operation = args.get("operation")
        if not device_id or not capability:
            raise _GateRejection(REJECT_INVALID_COMMAND)
        if operation != APPLY_OPERATION:
            raise _GateRejection(REJECT_UNSUPPORTED_CAPABILITY)
        if step.target_device_id is not None and step.target_device_id != device_id:
            raise _GateRejection(REJECT_INVALID_COMMAND)
        if step.capability_name is not None and step.capability_name != capability:
            raise _GateRejection(REJECT_INVALID_COMMAND)
        if capability not in ALLOWED_CAPABILITIES:
            raise _GateRejection(REJECT_UNSUPPORTED_CAPABILITY)

        parameters = args.get("parameters", {})
        if not isinstance(parameters, dict) or not self._validate_parameters(parameters):
            raise _GateRejection(REJECT_INVALID_ARGUMENTS)
        return command, device_id, capability, parameters

    def _validate_parameters(self, parameters: dict) -> bool:
        if not isinstance(parameters, dict) or len(parameters) != 1:
            return False
        if POWER_SWITCH_ARGUMENT not in parameters:
            return False
        value = parameters[POWER_SWITCH_ARGUMENT]
        return isinstance(value, str) and value in ALLOWED_POWER_SWITCH_STATES

    def _verify_availability(self, device_id, capability_name) -> None:
        registry = getattr(getattr(self.runtime, "context", None), "device_registry", None)
        if registry is None:
            raise _GateRejection(REJECT_DEVICE_UNAVAILABLE)
        try:
            device = registry.get(device_id)
        except KeyError:
            raise _GateRejection(REJECT_DEVICE_UNAVAILABLE)
        for capability in device.capabilities:
            if (
                isinstance(capability, DeviceCapability)
                and capability.name == capability_name
                and capability.kind == "action"
            ):
                return
        raise _GateRejection(REJECT_CAPABILITY_UNAVAILABLE)

    def _rejected(self, reason: str, error):
        return ExecutionGateResult(
            status=GATE_STATUS_REJECTED,
            success=False,
            commands_executed=False,
            device_id=None,
            capability=None,
            arguments=None,
            confirmation_id=None,
            plan_digest=None,
            runtime_result=None,
            error=error,
            message=REJECT_MESSAGE,
            reason=reason,
        )

    def _execution_failed_after_attempt(
        self,
        *,
        confirmation_id,
        plan_digest,
        device_id,
        capability,
        parameters,
    ):
        result = CapabilityResult(
            success=False,
            message=RUNTIME_FAILURE_MESSAGE,
            data={"device_id": device_id, "capability": capability},
            error=RUNTIME_EXECUTION_FAILED,
        )
        return ExecutionGateResult(
            status=GATE_STATUS_EXECUTION_FAILED,
            success=False,
            commands_executed=True,
            device_id=device_id,
            capability=capability,
            arguments=dict(parameters),
            confirmation_id=confirmation_id,
            plan_digest=plan_digest,
            runtime_result=result,
            error=RUNTIME_EXECUTION_FAILED,
            message=RUNTIME_FAILURE_MESSAGE,
            reason=None,
        )


class _GateRejection(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _optional_label(value, label: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{label} must be None or a non-empty string")


__all__ = [
    "ALLOWED_CAPABILITIES",
    "ALLOWED_POWER_SWITCH_STATES",
    "AI_CONFIRMATION_REQUIRED",
    "AI_EXECUTION_NOT_CONFIRMED",
    "EXECUTION_GATE_SOURCE",
    "ExecutionGate",
    "ExecutionGateResult",
    "GATE_STATUS_CANCELLED",
    "GATE_STATUS_CONFIRMATION_REQUIRED",
    "GATE_STATUS_EXECUTED",
    "GATE_STATUS_EXECUTION_FAILED",
    "GATE_STATUS_REJECTED",
    "GATE_STATUSES",
    "POWER_SWITCH_ARGUMENT",
    "POWER_SWITCH_PARAMETER_SETS",
    "REJECT_CAPABILITY_UNAVAILABLE",
    "REJECT_CONFIRMATION_DIGEST_MISMATCH",
    "REJECT_CONFIRMATION_NOT_FOUND",
    "REJECT_DECISION_CLAIMS_EXECUTION",
    "REJECT_DECISION_NOT_EXECUTABLE",
    "REJECT_DEVICE_UNAVAILABLE",
    "REJECT_INVALID_ARGUMENTS",
    "REJECT_INVALID_COMMAND",
    "REJECT_MISSING_EXECUTE_PLAN",
    "REJECT_MULTI_STEP_PLAN",
    "REJECT_REASONS",
    "REJECT_UNSUPPORTED_CAPABILITY",
    "REJECT_UNSUPPORTED_DECISION",
]