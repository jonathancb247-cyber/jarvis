"""Adapter-local confirmation state for AI plans."""

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from jarvis_core.ai.contracts import (
    AI_EXECUTION_NOT_CONFIRMED,
    AIConfirmationState,
)
from jarvis_core.ai.validation import AIValidationError


class AIConfirmationStore:
    """Single-pending-plan confirmation store for one adapter instance."""

    def __init__(self):
        self.pending = None
        self.pending_plan = None

    def create(self, plan):
        state = AIConfirmationState(
            pending_plan_id=str(uuid4()),
            normalized_plan_digest=plan_digest(plan),
            safe_summary=plan.safe_summary,
            steps=plan.steps,
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=None,
            confirmed=False,
        )
        self.pending = state
        self.pending_plan = plan
        return state

    def confirm(self, plan_id, normalized_plan_digest=None):
        if self.pending is None or self.pending_plan is None:
            raise AIValidationError(AI_EXECUTION_NOT_CONFIRMED)
        if self.pending.pending_plan_id != plan_id:
            raise AIValidationError(AI_EXECUTION_NOT_CONFIRMED)
        if (
            normalized_plan_digest is not None
            and self.pending.normalized_plan_digest != normalized_plan_digest
        ):
            raise AIValidationError(AI_EXECUTION_NOT_CONFIRMED)
        self.pending = replace(self.pending, confirmed=True)
        return self.pending_plan

    def consume(self):
        plan = self.pending_plan
        self.pending = None
        self.pending_plan = None
        return plan

    def cancel(self, plan_id):
        if self.pending is None or self.pending.pending_plan_id != plan_id:
            raise AIValidationError(AI_EXECUTION_NOT_CONFIRMED)
        self.pending = None
        self.pending_plan = None


def plan_digest(plan):
    payload = {
        "schema_version": plan.schema_version,
        "kind": plan.kind,
        "safe_summary": plan.safe_summary,
        "steps": [
            {
                "index": step.index,
                "canonical_command_text": step.canonical_command_text,
                "safe_description": step.safe_description,
                "target_device_id": step.target_device_id,
                "capability_name": step.capability_name,
                "action_kind": step.action_kind,
                "requires_confirmation": step.requires_confirmation,
                "policy_flags": list(step.policy_flags),
            }
            for step in plan.steps
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
