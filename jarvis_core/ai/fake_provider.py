"""Deterministic fake provider for AI Adapter boundary validation."""


class DeterministicFakeAIProvider:
    """Return predetermined provider-like payloads with no network or credentials."""

    def __init__(self, responses=None):
        self.responses = responses or default_responses()
        self.calls = []

    def generate(self, user_request, safe_context):
        self.calls.append({"user_request": user_request, "safe_context": safe_context})
        return self.responses.get(user_request, default_refusal())


def default_responses():
    return {
        "read lamp": execute_plan(
            "Read lamp status.",
            [
                step(
                    0,
                    "device read lamp_1 status.read",
                    "Read lamp status.",
                    "lamp_1",
                    "status.read",
                    "read",
                )
            ],
        ),
        "turn lamp on": execute_plan(
            "Turn lamp on.",
            [
                step(
                    0,
                    "device apply lamp_1 power.switch state=true",
                    "Turn lamp on.",
                    "lamp_1",
                    "power.switch",
                    "mutate",
                )
            ],
        ),
        "turn lamp off": execute_plan(
            "Turn lamp off.",
            [
                step(
                    0,
                    "device apply lamp_1 power.switch state=false",
                    "Turn lamp off.",
                    "lamp_1",
                    "power.switch",
                    "mutate",
                )
            ],
        ),
        "read then turn lamp on": execute_plan(
            "Read lamp and then turn it on.",
            [
                step(
                    0,
                    "device read lamp_1 status.read",
                    "Read lamp status.",
                    "lamp_1",
                    "status.read",
                    "read",
                ),
                step(
                    1,
                    "device apply lamp_1 power.switch state=true",
                    "Turn lamp on.",
                    "lamp_1",
                    "power.switch",
                    "mutate",
                ),
            ],
        ),
        "which lamp": {
            "schema_version": 1,
            "kind": "clarify",
            "steps": [],
            "safe_summary": "Need a target device.",
            "clarification": {
                "question": "Which lamp should I use?",
                "reason_code": "ambiguous_device",
                "missing_fields": ["device_id"],
                "candidate_options": ["lamp_1"],
            },
            "refusal": None,
            "confirmation_required": False,
            "policy_flags": [],
        },
        "do forbidden thing": default_refusal(),
        "malformed response": {"kind": "execute"},
        "unsafe command": execute_plan(
            "Unsafe command.",
            [step(0, "device read lamp_1 status.read; rm -rf", "Unsafe command.")],
        ),
        "hidden mutation": execute_plan(
            "Hidden mutation.",
            [
                step(
                    0,
                    "device apply lamp_1 power.switch state=true",
                    "Looks read-only.",
                    "lamp_1",
                    "power.switch",
                    "read",
                )
            ],
        ),
    }


def execute_plan(summary, steps):
    return {
        "schema_version": 1,
        "kind": "execute",
        "steps": steps,
        "safe_summary": summary,
        "clarification": None,
        "refusal": None,
        "confirmation_required": False,
        "policy_flags": [],
    }


def step(
    index,
    command,
    description,
    target_device_id=None,
    capability_name=None,
    action_kind="unknown",
):
    return {
        "index": index,
        "canonical_command_text": command,
        "safe_description": description,
        "target_device_id": target_device_id,
        "capability_name": capability_name,
        "action_kind": action_kind,
        "requires_confirmation": False,
        "policy_flags": [],
    }


def default_refusal():
    return {
        "schema_version": 1,
        "kind": "refuse",
        "steps": [],
        "safe_summary": "Request refused.",
        "clarification": None,
        "refusal": {
            "safe_message": "I cannot safely perform that request.",
            "reason_code": "unsupported_operation",
        },
        "confirmation_required": False,
        "policy_flags": [],
    }
