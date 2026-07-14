"""Immutable adapter-layer contracts for the experimental AI boundary."""

from dataclasses import dataclass, field


PLAN_SCHEMA_VERSION = 1
PLAN_KIND_EXECUTE = "execute"
PLAN_KIND_CLARIFY = "clarify"
PLAN_KIND_REFUSE = "refuse"
PLAN_KINDS = {PLAN_KIND_EXECUTE, PLAN_KIND_CLARIFY, PLAN_KIND_REFUSE}

ACTION_KIND_READ = "read"
ACTION_KIND_MUTATE = "mutate"
ACTION_KIND_UNKNOWN = "unknown"
ACTION_KINDS = {ACTION_KIND_READ, ACTION_KIND_MUTATE, ACTION_KIND_UNKNOWN}

MAX_CONTEXT_DEVICES = 32
MAX_CAPABILITIES_PER_DEVICE = 32
MAX_PLAN_STEPS = 5
MAX_CLARIFICATION_OPTIONS = 5
MAX_USER_REQUEST_LENGTH = 4096
MAX_SAFE_TEXT_LENGTH = 512
MAX_COMMAND_LENGTH = 512
MAX_PREVIOUS_RESULTS = 5
MAX_PROPERTIES_PER_DEVICE = 32

AI_PROVIDER_UNAVAILABLE = "ai_provider_unavailable"
AI_RESPONSE_INVALID = "ai_response_invalid"
AI_PLAN_REJECTED = "ai_plan_rejected"
AI_POLICY_VIOLATION = "ai_policy_violation"
AI_CLARIFICATION_REQUIRED = "ai_clarification_required"
AI_CONFIRMATION_REQUIRED = "ai_confirmation_required"
AI_EXECUTION_NOT_CONFIRMED = "ai_execution_not_confirmed"

CLARIFICATION_REASON_CODES = {
    "ambiguous_device",
    "missing_parameter",
    "unsupported_request",
    "multiple_possible_actions",
    "safety_uncertainty",
    "insufficient_context",
}

REFUSAL_REASON_CODES = {
    "forbidden_operation",
    "policy_violation",
    "unsafe_request",
    "unsupported_operation",
    "invalid_provider_output",
}


@dataclass(frozen=True)
class AIActionStep:
    index: int
    canonical_command_text: str
    safe_description: str
    target_device_id: str = None
    capability_name: str = None
    action_kind: str = ACTION_KIND_UNKNOWN
    requires_confirmation: bool = False
    policy_flags: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.index, int) or self.index < 0:
            raise ValueError("AIActionStep index must be a non-negative int")
        _require_bounded_string(
            self.canonical_command_text,
            "AIActionStep canonical_command_text",
            MAX_COMMAND_LENGTH,
        )
        _require_bounded_string(
            self.safe_description,
            "AIActionStep safe_description",
            MAX_SAFE_TEXT_LENGTH,
        )
        _validate_optional_bounded_string(self.target_device_id, "target_device_id")
        _validate_optional_bounded_string(self.capability_name, "capability_name")
        if self.action_kind not in ACTION_KINDS:
            raise ValueError("AIActionStep action_kind is invalid")
        if not isinstance(self.requires_confirmation, bool):
            raise ValueError("AIActionStep requires_confirmation must be a bool")
        _validate_string_tuple(self.policy_flags, "AIActionStep policy_flags")


@dataclass(frozen=True)
class AIClarification:
    question: str
    reason_code: str
    missing_fields: tuple = field(default_factory=tuple)
    candidate_options: tuple = field(default_factory=tuple)

    def __post_init__(self):
        _require_bounded_string(self.question, "AIClarification question")
        if self.reason_code not in CLARIFICATION_REASON_CODES:
            raise ValueError("AIClarification reason_code is invalid")
        _validate_string_tuple(self.missing_fields, "AIClarification missing_fields")
        _validate_string_tuple(
            self.candidate_options,
            "AIClarification candidate_options",
            max_items=MAX_CLARIFICATION_OPTIONS,
        )


@dataclass(frozen=True)
class AIRefusal:
    safe_message: str
    reason_code: str

    def __post_init__(self):
        _require_bounded_string(self.safe_message, "AIRefusal safe_message")
        if self.reason_code not in REFUSAL_REASON_CODES:
            raise ValueError("AIRefusal reason_code is invalid")


@dataclass(frozen=True)
class AIActionPlan:
    schema_version: int
    kind: str
    steps: tuple = field(default_factory=tuple)
    safe_summary: str = ""
    clarification: AIClarification = None
    refusal: AIRefusal = None
    confirmation_required: bool = False
    policy_flags: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if self.schema_version != PLAN_SCHEMA_VERSION:
            raise ValueError("AIActionPlan schema_version is unsupported")
        if self.kind not in PLAN_KINDS:
            raise ValueError("AIActionPlan kind is invalid")
        if not isinstance(self.steps, tuple):
            raise ValueError("AIActionPlan steps must be a tuple")
        for step in self.steps:
            if not isinstance(step, AIActionStep):
                raise ValueError("AIActionPlan steps must contain AIActionStep")
        if self.safe_summary:
            _require_bounded_string(self.safe_summary, "AIActionPlan safe_summary")
        if self.clarification is not None and not isinstance(
            self.clarification,
            AIClarification,
        ):
            raise ValueError("AIActionPlan clarification is invalid")
        if self.refusal is not None and not isinstance(self.refusal, AIRefusal):
            raise ValueError("AIActionPlan refusal is invalid")
        if not isinstance(self.confirmation_required, bool):
            raise ValueError("AIActionPlan confirmation_required must be a bool")
        _validate_string_tuple(self.policy_flags, "AIActionPlan policy_flags")
        self._validate_kind_shape()

    def _validate_kind_shape(self):
        if self.kind == PLAN_KIND_EXECUTE:
            if not 1 <= len(self.steps) <= MAX_PLAN_STEPS:
                raise ValueError("execute plans require one to five steps")
            if self.clarification is not None or self.refusal is not None:
                raise ValueError("execute plans cannot include clarification or refusal")
            return
        if self.steps:
            raise ValueError("non-execute plans cannot include executable steps")
        if self.confirmation_required:
            raise ValueError("non-execute plans cannot require confirmation")
        if self.kind == PLAN_KIND_CLARIFY:
            if self.clarification is None or self.refusal is not None:
                raise ValueError("clarify plans require clarification only")
            return
        if self.refusal is None or self.clarification is not None:
            raise ValueError("refuse plans require refusal only")


@dataclass(frozen=True)
class AISafeCapability:
    name: str
    kind: str
    parameters: tuple = field(default_factory=tuple)

    def __post_init__(self):
        _require_bounded_string(self.name, "AISafeCapability name")
        if self.kind not in {"action", "reading"}:
            raise ValueError("AISafeCapability kind is invalid")
        if not isinstance(self.parameters, tuple):
            raise ValueError("AISafeCapability parameters must be a tuple")


@dataclass(frozen=True)
class AISafeDeviceState:
    status: str
    semantic_properties: tuple = field(default_factory=tuple)
    updated_at: str = None

    def __post_init__(self):
        _require_bounded_string(self.status, "AISafeDeviceState status")
        if not isinstance(self.semantic_properties, tuple):
            raise ValueError("AISafeDeviceState semantic_properties must be a tuple")
        if len(self.semantic_properties) > MAX_PROPERTIES_PER_DEVICE:
            raise ValueError("AISafeDeviceState has too many properties")
        _validate_optional_bounded_string(self.updated_at, "updated_at")


@dataclass(frozen=True)
class AISafeDevice:
    device_id: str
    display_name: str
    device_type: str
    capabilities: tuple = field(default_factory=tuple)
    state: AISafeDeviceState = None

    def __post_init__(self):
        _require_bounded_string(self.device_id, "AISafeDevice device_id")
        _require_bounded_string(self.display_name, "AISafeDevice display_name")
        _require_bounded_string(self.device_type, "AISafeDevice device_type")
        if not isinstance(self.capabilities, tuple):
            raise ValueError("AISafeDevice capabilities must be a tuple")
        if len(self.capabilities) > MAX_CAPABILITIES_PER_DEVICE:
            raise ValueError("AISafeDevice has too many capabilities")
        for capability in self.capabilities:
            if not isinstance(capability, AISafeCapability):
                raise ValueError("AISafeDevice capabilities are invalid")
        if not isinstance(self.state, AISafeDeviceState):
            raise ValueError("AISafeDevice state is required")


@dataclass(frozen=True)
class AISafePolicyContext:
    max_plan_steps: int = MAX_PLAN_STEPS
    confirmation_required_for_mutations: bool = True


@dataclass(frozen=True)
class AISafeResult:
    step_index: int
    success: bool
    message: str
    error: str = None

    def __post_init__(self):
        if not isinstance(self.step_index, int) or self.step_index < 0:
            raise ValueError("AISafeResult step_index must be a non-negative int")
        if not isinstance(self.success, bool):
            raise ValueError("AISafeResult success must be a bool")
        _require_bounded_string(self.message, "AISafeResult message")
        _validate_optional_bounded_string(self.error, "AISafeResult error")


@dataclass(frozen=True)
class AISafeContext:
    schema_version: int
    user_request: str
    session_context: tuple = field(default_factory=tuple)
    devices: tuple = field(default_factory=tuple)
    command_grammar: tuple = field(default_factory=tuple)
    policies: AISafePolicyContext = field(default_factory=AISafePolicyContext)
    previous_results: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if self.schema_version != PLAN_SCHEMA_VERSION:
            raise ValueError("AISafeContext schema_version is unsupported")
        _require_bounded_string(
            self.user_request,
            "AISafeContext user_request",
            MAX_USER_REQUEST_LENGTH,
        )
        if not isinstance(self.session_context, tuple):
            raise ValueError("AISafeContext session_context must be a tuple")
        if not isinstance(self.devices, tuple):
            raise ValueError("AISafeContext devices must be a tuple")
        if len(self.devices) > MAX_CONTEXT_DEVICES:
            raise ValueError("AISafeContext has too many devices")
        for device in self.devices:
            if not isinstance(device, AISafeDevice):
                raise ValueError("AISafeContext devices are invalid")
        if not isinstance(self.command_grammar, tuple):
            raise ValueError("AISafeContext command_grammar must be a tuple")
        if not isinstance(self.policies, AISafePolicyContext):
            raise ValueError("AISafeContext policies is invalid")
        if not isinstance(self.previous_results, tuple):
            raise ValueError("AISafeContext previous_results must be a tuple")
        if len(self.previous_results) > MAX_PREVIOUS_RESULTS:
            raise ValueError("AISafeContext previous_results is too large")


@dataclass(frozen=True)
class AIConfirmationState:
    pending_plan_id: str
    normalized_plan_digest: str
    safe_summary: str
    steps: tuple
    created_at: str
    expires_at: str = None
    confirmed: bool = False

    def __post_init__(self):
        _require_bounded_string(self.pending_plan_id, "pending_plan_id")
        _require_bounded_string(self.normalized_plan_digest, "normalized_plan_digest")
        _require_bounded_string(self.safe_summary, "safe_summary")
        if not isinstance(self.steps, tuple):
            raise ValueError("AIConfirmationState steps must be a tuple")
        _require_bounded_string(self.created_at, "created_at")
        _validate_optional_bounded_string(self.expires_at, "expires_at")
        if not isinstance(self.confirmed, bool):
            raise ValueError("AIConfirmationState confirmed must be a bool")


@dataclass(frozen=True)
class AIPlanExecutionSummary:
    completed_steps: int
    failed_step_index: int = None
    safe_step_results: tuple = field(default_factory=tuple)
    overall_success: bool = False
    safe_message: str = ""

    def __post_init__(self):
        if not isinstance(self.completed_steps, int) or self.completed_steps < 0:
            raise ValueError("completed_steps must be a non-negative int")
        if self.failed_step_index is not None and (
            not isinstance(self.failed_step_index, int) or self.failed_step_index < 0
        ):
            raise ValueError("failed_step_index must be None or a non-negative int")
        if not isinstance(self.safe_step_results, tuple):
            raise ValueError("safe_step_results must be a tuple")
        if not isinstance(self.overall_success, bool):
            raise ValueError("overall_success must be a bool")
        if self.safe_message:
            _require_bounded_string(self.safe_message, "safe_message")


@dataclass(frozen=True)
class AIAdapterResult:
    status: str
    success: bool = False
    plan: AIActionPlan = None
    execution_summary: AIPlanExecutionSummary = None
    clarification: AIClarification = None
    refusal: AIRefusal = None
    error: str = None
    message: str = ""

    def __post_init__(self):
        _require_bounded_string(self.status, "AIAdapterResult status")
        if not isinstance(self.success, bool):
            raise ValueError("AIAdapterResult success must be a bool")
        _validate_optional_bounded_string(self.error, "AIAdapterResult error")
        if self.message:
            _require_bounded_string(self.message, "AIAdapterResult message")


def _require_bounded_string(value, label, max_length=MAX_SAFE_TEXT_LENGTH):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > max_length:
        raise ValueError(f"{label} exceeds maximum length")


def _validate_optional_bounded_string(value, label):
    if value is None:
        return
    _require_bounded_string(value, label)


def _validate_string_tuple(value, label, max_items=None):
    if not isinstance(value, tuple):
        raise ValueError(f"{label} must be a tuple")
    if max_items is not None and len(value) > max_items:
        raise ValueError(f"{label} has too many items")
    for item in value:
        _require_bounded_string(item, label)
