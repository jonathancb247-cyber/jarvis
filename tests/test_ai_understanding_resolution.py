import ast
import unittest

from jarvis_core.ai.contracts import (
    ACTION_KIND_MUTATE,
    ACTION_KIND_READ,
    AI_PLAN_REJECTED,
    AI_RESPONSE_INVALID,
    PLAN_KIND_CLARIFY,
    PLAN_KIND_EXECUTE,
    PLAN_KIND_REFUSE,
    PLAN_SCHEMA_VERSION,
    AISafeCapability,
    AISafeContext,
    AISafeDevice,
    AISafeDeviceState,
)
from jarvis_core.ai.understanding import (
    AIUnderstandingProposal,
    normalize_understanding_proposal,
)
from jarvis_core.ai.understanding_resolution import DeterministicUnderstandingResolver
from jarvis_core.ai.validation import AIValidationError


class AIUnderstandingNormalizationTests(unittest.TestCase):
    def test_malformed_proposal_cannot_produce_execute(self):
        with self.assertRaises(AIValidationError) as raised:
            normalize_understanding_proposal(
                {
                    "intent": "read",
                    "referenced_device_id": "lamp_1",
                    "capability_hint": "status.read",
                    "extra": "not allowed",
                }
            )
        self.assertEqual(raised.exception.code, AI_RESPONSE_INVALID)

    def test_confidence_is_bounded_metadata_only(self):
        proposal = normalize_understanding_proposal(
            {
                "intent": "read",
                "referenced_device_id": "lamp_99",
                "capability_hint": "status.read",
                "confidence": 1.0,
            }
        )

        plan = resolver().resolve(safe_context(), proposal)

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_confidence_out_of_range_is_invalid(self):
        with self.assertRaises(AIValidationError):
            normalize_understanding_proposal(
                {
                    "intent": "read",
                    "confidence": 1.1,
                }
            )

    def test_duplicate_raw_argument_same_values_is_invalid(self):
        with self.assertRaises(AIValidationError):
            normalize_understanding_proposal(
                {
                    "intent": "mutate",
                    "referenced_device_id": "lamp_1",
                    "capability_hint": "power.switch",
                    "raw_arguments": [["state", "true"], ["state", "true"]],
                }
            )

    def test_duplicate_raw_argument_conflicting_values_is_invalid(self):
        with self.assertRaises(AIValidationError):
            normalize_understanding_proposal(
                {
                    "intent": "mutate",
                    "referenced_device_id": "lamp_1",
                    "capability_hint": "power.switch",
                    "raw_arguments": [["state", "false"], ["state", "true"]],
                }
            )


class DeterministicUnderstandingResolverTests(unittest.TestCase):
    def test_exact_device_and_reading_capability_resolves_execute(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
                operation_hint="read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].canonical_command_text, "device read lamp_1 status.read")
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")
        self.assertEqual(plan.steps[0].capability_name, "status.read")
        self.assertEqual(plan.steps[0].action_kind, ACTION_KIND_READ)
        self.assertFalse(plan.confirmation_required)

    def test_unique_display_name_resolution_resolves_execute(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_text="Lamp",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].canonical_command_text, "device read lamp_1 status.read")

    def test_matching_referenced_device_id_and_text_resolves_execute(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                referenced_device_text="Lamp",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_conflicting_referenced_device_id_and_text_resolves_clarify(self):
        plan = resolver().resolve(
            safe_context(include_second_lamp=True),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                referenced_device_text="Desk Lamp",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_valid_id_and_unknown_text_resolves_clarify(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                referenced_device_text="Garage Sensor",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_valid_id_and_ambiguous_text_resolves_clarify(self):
        plan = resolver().resolve(
            safe_context(include_second_lamp=True),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                referenced_device_text="light",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_high_confidence_cannot_override_conflicting_device_hints(self):
        plan = resolver().resolve(
            safe_context(include_second_lamp=True),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                referenced_device_text="Desk Lamp",
                capability_hint="status.read",
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_ambiguous_two_device_match_resolves_clarify_in_deterministic_order(self):
        plan = resolver().resolve(
            safe_context(include_second_lamp=True),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.clarification.reason_code, "ambiguous_device")
        self.assertEqual(plan.clarification.candidate_options, ("lamp_1", "lamp_2"))
        self.assertEqual(plan.steps, ())

    def test_device_type_ambiguity_is_deterministic(self):
        first = resolver().resolve(
            safe_context(include_second_lamp=True),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_text="light",
                capability_hint="status.read",
            ),
        )
        second = resolver().resolve(
            safe_context(include_second_lamp=True),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_text="light",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(first.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(first.clarification.candidate_options, ("lamp_1", "lamp_2"))
        self.assertEqual(first, second)

    def test_fabricated_referenced_device_id_never_executes(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_text="Lamp",
                referenced_device_id="lamp_99",
                capability_hint="status.read",
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.clarification.reason_code, "insufficient_context")
        self.assertEqual(plan.steps, ())

    def test_valid_action_with_required_argument_resolves_mutating_execute(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                operation_hint="apply",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(
            plan.steps[0].canonical_command_text,
            "device apply lamp_1 power.switch state=true",
        )
        self.assertEqual(plan.steps[0].action_kind, ACTION_KIND_MUTATE)
        self.assertTrue(plan.steps[0].requires_confirmation)
        self.assertTrue(plan.confirmation_required)

    def test_missing_required_state_resolves_clarify_missing_parameter(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.clarification.reason_code, "missing_parameter")
        self.assertEqual(plan.clarification.missing_fields, ("state",))

    def test_invalid_capability_does_not_execute(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="battery.level",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.clarification.reason_code, "unsupported_request")
        self.assertEqual(plan.steps, ())

    def test_destructive_request_resolves_refuse_from_user_request(self):
        plan = resolver().resolve(
            safe_context(user_request="Borra todos los dispositivos."),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_REFUSE)
        self.assertEqual(plan.refusal.reason_code, "forbidden_operation")
        self.assertEqual(plan.steps, ())

    def test_llm_clarify_hint_cannot_override_sufficient_context(self):
        plan = resolver().resolve(
            safe_context(),
            AIUnderstandingProposal(
                intent="clarify",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
                safety_hints=("insufficient_context",),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].canonical_command_text, "device read lamp_1 status.read")

    def test_generated_command_is_validated_with_existing_planner(self):
        bad_context = safe_context(
            capabilities=(
                AISafeCapability(
                    name="bad;capability",
                    kind="reading",
                    parameters=(),
                ),
            )
        )

        with self.assertRaises(AIValidationError) as raised:
            resolver().resolve(
                bad_context,
                AIUnderstandingProposal(
                    intent="read",
                    referenced_device_id="lamp_1",
                    capability_hint="bad;capability",
                ),
            )
        self.assertEqual(raised.exception.code, AI_PLAN_REJECTED)

    def test_unsafe_argument_key_cannot_become_executable_command(self):
        with self.assertRaises(AIValidationError) as raised:
            resolver().resolve(
                safe_context(),
                AIUnderstandingProposal(
                    intent="mutate",
                    referenced_device_id="lamp_1",
                    capability_hint="power.switch",
                    raw_arguments=(("state", "true"), ("mode;rm", "fast")),
                ),
            )
        self.assertEqual(raised.exception.code, AI_PLAN_REJECTED)

    def test_unsafe_argument_value_cannot_become_executable_command(self):
        with self.assertRaises(AIValidationError) as raised:
            resolver().resolve(
                safe_context(),
                AIUnderstandingProposal(
                    intent="mutate",
                    referenced_device_id="lamp_1",
                    capability_hint="power.switch",
                    raw_arguments=(("state", "true && device remove lamp_1"),),
                ),
            )
        self.assertEqual(raised.exception.code, AI_PLAN_REJECTED)

    def test_provider_and_resolver_do_not_import_execution_boundaries(self):
        for path in (
            "jarvis_core/ai/understanding.py",
            "jarvis_core/ai/understanding_resolution.py",
        ):
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imports.update(
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            )
            forbidden = {
                "jarvis_core.runtime",
                "jarvis_core.drivers",
                "jarvis_core.http_driver",
                "jarvis_core.mqtt_driver",
                "jarvis_core.voice",
                "jarvis_core.api",
                "jarvis_core.dashboard",
            }
            self.assertFalse(imports & forbidden)


def resolver():
    return DeterministicUnderstandingResolver()


def safe_context(
    *,
    user_request="Lee el estado de lamp_1.",
    include_second_lamp=False,
    capabilities=None,
):
    devices = [
        safe_device(
            "lamp_1",
            "Lamp",
            "light",
            capabilities=capabilities or default_capabilities(),
        )
    ]
    if include_second_lamp:
        devices.append(
            safe_device(
                "lamp_2",
                "Desk Lamp",
                "light",
                capabilities=default_capabilities(),
            )
        )
    return AISafeContext(
        schema_version=PLAN_SCHEMA_VERSION,
        user_request=user_request,
        devices=tuple(devices),
        command_grammar=(),
    )


def safe_device(device_id, display_name, device_type, *, capabilities):
    return AISafeDevice(
        device_id=device_id,
        display_name=display_name,
        device_type=device_type,
        capabilities=tuple(capabilities),
        state=AISafeDeviceState(status="known", semantic_properties=(("power", False),)),
    )


def default_capabilities():
    return (
        AISafeCapability(name="status.read", kind="reading", parameters=()),
        AISafeCapability(
            name="power.switch",
            kind="action",
            parameters=(
                (
                    ("name", "state"),
                    ("required", True),
                    ("type", "boolean"),
                ),
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
