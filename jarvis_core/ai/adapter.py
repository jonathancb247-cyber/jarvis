"""Deterministic fake AI Adapter boundary."""

from jarvis_core.ai.confirmation import AIConfirmationStore
from jarvis_core.ai.context import SafeContextBuilder
from jarvis_core.ai.contracts import (
    ACTION_KIND_READ,
    AI_CLARIFICATION_REQUIRED,
    AI_CONFIRMATION_REQUIRED,
    AI_EXECUTION_NOT_CONFIRMED,
    AI_PLAN_REJECTED,
    AI_RESPONSE_INVALID,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
    AIAdapterResult,
    AIPlanExecutionSummary,
    AISafeResult,
)
from jarvis_core.ai.fake_provider import DeterministicFakeAIProvider
from jarvis_core.ai.ollama import OllamaProviderError
from jarvis_core.ai.validation import (
    AIValidationError,
    classify_command,
    normalize_plan,
    recompute_plan,
    recompute_step,
    validate_against_context,
    validate_command_text_safety,
    validate_plan_shape,
    validate_with_planner,
)
from jarvis_core.domain import CapabilityResult


class FakeAIAdapter:
    """Adapter that validates deterministic fake AI plans before Runtime entry."""

    def __init__(
        self,
        runtime,
        provider=None,
        context_builder=None,
        confirmation_store=None,
    ):
        self.runtime = runtime
        self.provider = provider or DeterministicFakeAIProvider()
        self.context_builder = context_builder or SafeContextBuilder()
        self.confirmation_store = confirmation_store or AIConfirmationStore()

    def propose(self, user_request, session_context=None):
        try:
            safe_context = self.context_builder.build(
                user_request,
                self.runtime.context.device_registry,
                session_context=session_context,
            )
            raw_plan = self._generate_provider_plan(user_request, safe_context)
            plan = self._validated_plan(raw_plan, safe_context)
        except OllamaProviderError as error:
            return self._error(error.code)
        except AIValidationError as error:
            record_adapter_error = getattr(self.provider, "record_adapter_error", None)
            if callable(record_adapter_error):
                record_adapter_error(error.code, error.reason)
            return self._error(error.code)

        if plan.kind == PLAN_KIND_CLARIFY:
            return AIAdapterResult(
                status="clarification_required",
                success=False,
                plan=plan,
                clarification=plan.clarification,
                error=AI_CLARIFICATION_REQUIRED,
                message=plan.clarification.question,
            )
        if plan.kind == PLAN_KIND_REFUSE:
            return AIAdapterResult(
                status="refused",
                success=False,
                plan=plan,
                refusal=plan.refusal,
                error=plan.refusal.reason_code,
                message=plan.refusal.safe_message,
            )
        if plan.confirmation_required:
            confirmation = self.confirmation_store.create(plan)
            return AIAdapterResult(
                status="confirmation_required",
                success=False,
                plan=plan,
                error=AI_CONFIRMATION_REQUIRED,
                message=confirmation.pending_plan_id,
            )
        return self._execute_plan(plan)

    def confirm(self, plan_id, normalized_plan_digest=None):
        try:
            plan = self.confirmation_store.confirm(plan_id, normalized_plan_digest)
        except AIValidationError as error:
            return self._error(error.code)
        result = self._execute_plan(plan)
        self.confirmation_store.consume()
        return result

    def cancel(self, plan_id):
        try:
            self.confirmation_store.cancel(plan_id)
        except AIValidationError as error:
            return self._error(error.code)
        return AIAdapterResult(
            status="cancelled",
            success=False,
            error=AI_EXECUTION_NOT_CONFIRMED,
            message="AI plan execution was not confirmed.",
        )

    def _validated_plan(self, raw_plan, safe_context):
        plan = validate_plan_shape(normalize_plan(raw_plan))
        if plan.kind != PLAN_KIND_EXECUTE:
            return plan

        recomputed_steps = []
        for step in plan.steps:
            validate_command_text_safety(step.canonical_command_text)
            command = validate_with_planner(self.runtime.planner, step.canonical_command_text)
            validate_against_context(step, command, safe_context)
            action_kind = classify_command(command, safe_context)
            if action_kind != ACTION_KIND_READ and action_kind not in {"mutate"}:
                raise AIValidationError(AI_PLAN_REJECTED)
            recomputed_steps.append(recompute_step(step, action_kind))
        return recompute_plan(plan, recomputed_steps)

    def _generate_provider_plan(self, user_request, safe_context):
        generate_plan = getattr(self.provider, "generate_plan", None)
        if callable(generate_plan):
            return generate_plan(safe_context)
        return self.provider.generate(user_request, safe_context)

    def _execute_plan(self, plan):
        safe_results = []
        completed = 0
        failed_step_index = None
        for step in plan.steps:
            result = self.runtime.handle_adapter_input(
                step.canonical_command_text,
                source="ai.adapter",
            )
            safe_result = self._safe_result(step.index, result)
            safe_results.append(safe_result)
            if not result.success:
                failed_step_index = step.index
                break
            completed += 1

        overall_success = failed_step_index is None
        summary = AIPlanExecutionSummary(
            completed_steps=completed,
            failed_step_index=failed_step_index,
            safe_step_results=tuple(safe_results),
            overall_success=overall_success,
            safe_message=(
                "AI plan completed."
                if overall_success
                else "AI plan stopped after a failed step."
            ),
        )
        return AIAdapterResult(
            status="executed" if overall_success else "execution_failed",
            success=overall_success,
            plan=plan,
            execution_summary=summary,
            error=None if overall_success else safe_results[-1].error,
            message=summary.safe_message,
        )

    def _safe_result(self, step_index, result):
        if not isinstance(result, CapabilityResult):
            return AISafeResult(
                step_index=step_index,
                success=False,
                message="Runtime returned an invalid result.",
                error=AI_PLAN_REJECTED,
            )
        return AISafeResult(
            step_index=step_index,
            success=result.success,
            message=result.message,
            error=result.error,
        )

    def _error(self, code):
        safe_code = code if isinstance(code, str) and code else AI_RESPONSE_INVALID
        return AIAdapterResult(
            status="error",
            success=False,
            error=safe_code,
            message="AI adapter request failed.",
        )
