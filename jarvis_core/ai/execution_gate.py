"""Safe local execution gate for validated local understanding decisions.

This module is the only approved boundary through which a non-executing
``LocalUnderstandingDecision`` may reach the existing deterministic Runtime.
It never trusts the AI-produced plan as an authority: it re-derives the
canonical command through the existing Planner and applies a strict allowlist
before anything reaches ``Runtime.execute``.

Design rules:

- Only ``EXECUTABLE_CANDIDATE`` decisions are eligible; clarify, refuse,
  unavailable and failed decisions are rejected before Runtime.
- A decision that claims ``commands_executed=True`` is rejected defensively
  (the decision surface itself already forbids constructing it).
- Only single-step execute plans are allowed; multi-step plans are rejected.
- The canonical command text is re-validated for safety and re-planned with
  the existing Planner; nothing trusts stored plan fields by themselves.
- Only the v1 allowlisted capability ``power.switch`` with a single ``state``
  argument in ``true/false/on/off`` can reach Runtime.
- ``executed=True`` means the command reached Runtime; device-level success or
  failure is surfaced via ``runtime_result`` and never hidden.

This module does not construct runtime authority by itself: Runtime remains
the sole execution boundary and the gate only forwards fully validated
commands to it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from jarvis_core.ai.contracts import PLAN_KIND_EXECUTE
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    LocalUnderstandingDecision,
)
from jarvis_core.ai.validation import AIValidationError, validate_command_text_safety
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
ALLOWED_POWER_SWITCH_STATES = frozenset({"true", "false", "on", "off"})
POWER_SWITCH_ARGUMENT = "state"

REJECT_UNSUPPORTED_DECISION = "unsupported_decision"
REJECT_DECISION_CLAIMS_EXECUTION = "decision_claims_execution"
REJECT_DECISION_NOT_EXECUTABLE = "decision_not_executable"
REJECT_MISSING_EXECUTE_PLAN = "missing_execute_plan"
REJECT_MULTI_STEP_PLAN = "multi_step_plan"
REJECT_INVALID_COMMAND = "invalid_command"
REJECT_UNSUPPORTED_CAPABILITY = "unsupported_capability"
REJECT_INVALID_ARGUMENTS = "invalid_arguments"

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
    }
)


@dataclass(frozen=True)
class ExecutionGateResult:
    """Immutable outcome of one gated local understanding execution."""

    executed: bool
    device_id: str | None = None
    capability: str | None = None
    arguments: dict | None = None
    runtime_result: CapabilityResult | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.executed, bool):
            raise ValueError("executed must be a bool")
        if self.executed:
            if self.runtime_result is None:
                raise ValueError("executed gate results require a runtime result")
            if not isinstance(self.runtime_result, CapabilityResult):
                raise ValueError("runtime_result must be a CapabilityResult")
            if self.reason is not None:
                raise ValueError("executed gate results cannot carry a reason")
            _require_label(self.device_id, "device_id")
            _require_label(self.capability, "capability")
            if not isinstance(self.arguments, dict):
                raise ValueError("executed gate results require arguments")
            return
        if self.runtime_result is not None:
            raise ValueError("rejected gate results cannot carry a runtime result")
        if self.reason not in REJECT_REASONS:
            raise ValueError("rejected gate results require a valid reason")
        if self.device_id is not None or self.capability is not None or self.arguments is not None:
            raise ValueError("rejected gate results cannot carry execution fields")


class ExecutionGate:
    """Allowlist and Planner boundary between understanding decisions and Runtime."""

    def __init__(self, runtime, planner=None):
        if not callable(getattr(runtime, "execute", None)):
            raise TypeError("ExecutionGate expects a runtime with execute(command)")
        self.runtime = runtime
        self.planner = planner or Planner()
        if not callable(getattr(self.planner, "plan", None)):
            raise TypeError("ExecutionGate expects a planner with plan(text)")

    def execute(self, decision) -> ExecutionGateResult:
        """Run the gated execution of a decision and always return an outcome."""
        if not isinstance(decision, LocalUnderstandingDecision):
            return self._rejected(REJECT_UNSUPPORTED_DECISION)
        if decision.commands_executed is not False:
            return self._rejected(REJECT_DECISION_CLAIMS_EXECUTION)
        if decision.status != EXECUTABLE_CANDIDATE:
            return self._rejected(REJECT_DECISION_NOT_EXECUTABLE)
        if decision.plan is None or decision.plan.kind != PLAN_KIND_EXECUTE:
            return self._rejected(REJECT_DECISION_NOT_EXECUTABLE)
        if len(decision.plan.steps) != 1:
            return self._rejected(REJECT_MULTI_STEP_PLAN)

        step = decision.plan.steps[0]
        command_text = step.canonical_command_text
        if not command_text or not command_text.strip():
            return self._rejected(REJECT_INVALID_COMMAND)
        try:
            validate_command_text_safety(command_text)
        except AIValidationError:
            return self._rejected(REJECT_INVALID_COMMAND)

        command = self.planner.plan(command_text, source=EXECUTION_GATE_SOURCE)
        if command.name != DEVICE_EXECUTE_COMMAND:
            return self._rejected(REJECT_INVALID_COMMAND)

        args = command.args
        device_id = args.get("device_id")
        capability = args.get("capability")
        operation = args.get("operation")
        if not device_id or not capability:
            return self._rejected(REJECT_INVALID_COMMAND)
        if step.target_device_id is not None and step.target_device_id != device_id:
            return self._rejected(REJECT_INVALID_COMMAND)
        if step.capability_name is not None and step.capability_name != capability:
            return self._rejected(REJECT_INVALID_COMMAND)
        if capability not in ALLOWED_CAPABILITIES or operation != APPLY_OPERATION:
            return self._rejected(REJECT_UNSUPPORTED_CAPABILITY)

        parameters = args.get("parameters", {})
        if not isinstance(parameters, dict) or not self._validate_arguments(parameters):
            return self._rejected(REJECT_INVALID_ARGUMENTS)

        result = self.runtime.execute(command)
        return ExecutionGateResult(
            executed=True,
            device_id=device_id,
            capability=capability,
            arguments=dict(parameters),
            runtime_result=result,
            reason=None,
        )

    def _validate_arguments(self, parameters: dict) -> bool:
        if set(parameters) != {POWER_SWITCH_ARGUMENT}:
            return False
        value = parameters[POWER_SWITCH_ARGUMENT]
        return value in ALLOWED_POWER_SWITCH_STATES

    def _rejected(self, reason: str) -> ExecutionGateResult:
        return ExecutionGateResult(
            executed=False,
            device_id=None,
            capability=None,
            arguments=None,
            runtime_result=None,
            reason=reason,
        )


def _require_label(value, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")


__all__ = [
    "ALLOWED_CAPABILITIES",
    "ALLOWED_POWER_SWITCH_STATES",
    "EXECUTION_GATE_SOURCE",
    "ExecutionGate",
    "ExecutionGateResult",
    "POWER_SWITCH_ARGUMENT",
    "REJECT_DECISION_CLAIMS_EXECUTION",
    "REJECT_DECISION_NOT_EXECUTABLE",
    "REJECT_INVALID_ARGUMENTS",
    "REJECT_INVALID_COMMAND",
    "REJECT_MISSING_EXECUTE_PLAN",
    "REJECT_MULTI_STEP_PLAN",
    "REJECT_REASONS",
    "REJECT_UNSUPPORTED_CAPABILITY",
    "REJECT_UNSUPPORTED_DECISION",
]