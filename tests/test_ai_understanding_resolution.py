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

    def test_direct_duplicate_raw_arguments_resolve_to_clarify_not_execute(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende power.switch del dispositivo lamp_1 con state true."
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"), ("state", "false")),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())


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
            safe_context(user_request="Lee el estado de Lamp."),
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
            safe_context(user_request="Lee el estado de Lamp lamp_1."),
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
            safe_context(
                user_request="Lee el estado de lamp_1 Desk Lamp.",
                include_second_lamp=True,
            ),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                referenced_device_text="Desk Lamp",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_valid_id_and_unknown_text_resolves_execute(self):
        plan = resolver().resolve(
            safe_context(user_request="Lee el estado de lamp_1."),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                referenced_device_text="Garage Sensor",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_valid_id_and_ungrounded_display_name_resolves_execute(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende power.switch del dispositivo lamp_1 con state true."
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                referenced_device_text="Lamp",
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

    def test_valid_id_and_ambiguous_text_resolves_clarify(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Lee el estado de lamp_1 light.",
                include_second_lamp=True,
            ),
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
            safe_context(
                user_request="Lee el estado de lamp_1 Desk Lamp.",
                include_second_lamp=True,
            ),
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

    def test_model_fabricated_id_from_generic_light_resolves_clarify(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz.",
                include_second_lamp=True,
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_explicit_device_id_is_grounded_and_allowed(self):
        plan = resolver().resolve(
            safe_context(user_request="Lee el estado de lamp_1."),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_device_id_embedded_in_larger_id_is_not_grounded(self):
        plan = resolver().resolve(
            safe_context(user_request="Lee el estado de lamp_10."),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_device_id_embedded_in_larger_token_is_not_grounded(self):
        plan = resolver().resolve(
            safe_context(user_request="Lee el estado de my_lamp_1_backup."),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_punctuation_around_explicit_device_id_is_grounded(self):
        plan = resolver().resolve(
            safe_context(user_request="Lee estado usando lamp_1."),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_ambiguous_two_device_match_resolves_clarify_in_deterministic_order(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz.",
                include_second_lamp=True,
            ),
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
            safe_context(
                user_request="Lee el estado de la luz.",
                include_second_lamp=True,
            ),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_text="light",
                capability_hint="status.read",
            ),
        )
        second = resolver().resolve(
            safe_context(
                user_request="Lee el estado de la luz.",
                include_second_lamp=True,
            ),
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
            safe_context(
                user_request="Enciende power.switch del dispositivo lamp_1 con state true."
            ),
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

    def test_missing_state_with_model_invented_value_resolves_clarify(self):
        plan = resolver().resolve(
            safe_context(user_request="Cambia power.switch del dispositivo lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "on"),),
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.clarification.reason_code, "missing_parameter")
        self.assertEqual(plan.clarification.missing_fields, ("state",))
        self.assertEqual(plan.steps, ())

    def test_explicit_state_value_is_grounded_and_allowed(self):
        plan = resolver().resolve(
            safe_context(user_request="Cambia power.switch del dispositivo lamp_1 state=on."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "on"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(
            plan.steps[0].canonical_command_text,
            "device apply lamp_1 power.switch state=on",
        )

    def test_explicit_state_equals_true_is_grounded(self):
        plan = resolver().resolve(
            safe_context(user_request="Cambia power.switch del dispositivo lamp_1 state=true."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(
            plan.steps[0].canonical_command_text,
            "device apply lamp_1 power.switch state=true",
        )

    def test_explicit_state_space_true_is_grounded(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Cambia power.switch del dispositivo lamp_1 con state true."
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)

    def test_state_value_embedded_in_larger_token_is_not_grounded(self):
        plan = resolver().resolve(
            safe_context(user_request="Cambia power.switch del dispositivo lamp_1 state=trueish."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_state_key_embedded_in_larger_token_is_not_grounded(self):
        plan = resolver().resolve(
            safe_context(user_request="Cambia power.switch del dispositivo lamp_1 mystate=true."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_positive_imperative_enciende_maps_to_state_true(self):
        plan = resolver().resolve(
            safe_context(user_request="Enciende lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(
            plan.steps[0].canonical_command_text,
            "device apply lamp_1 power.switch state=true",
        )

    def test_positive_imperative_apaga_maps_to_state_false(self):
        plan = resolver().resolve(
            safe_context(user_request="Apaga lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "false"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(
            plan.steps[0].canonical_command_text,
            "device apply lamp_1 power.switch state=false",
        )

    def test_positive_imperative_turn_on_maps_to_state_true(self):
        plan = resolver().resolve(
            safe_context(user_request="Turn on lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)

    def test_positive_imperative_turn_off_maps_to_state_false(self):
        plan = resolver().resolve(
            safe_context(user_request="Turn off lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "false"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)

    def test_negated_spanish_enciende_does_not_ground_power_switch(self):
        plan = resolver().resolve(
            safe_context(user_request="No enciendas lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_negated_english_turn_on_does_not_ground_power_switch(self):
        plan = resolver().resolve(
            safe_context(user_request="Do not turn on lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_non_imperative_spanish_no_enciende_does_not_ground_power_switch(self):
        plan = resolver().resolve(
            safe_context(user_request="lamp_1 no enciende."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_english_state_question_does_not_ground_power_switch(self):
        plan = resolver().resolve(
            safe_context(user_request="Is lamp_1 on?"),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_spanish_state_question_does_not_ground_power_switch(self):
        for user_request in ("¿lamp_1 está encendida?", "¿está encendida lamp_1?"):
            with self.subTest(user_request=user_request):
                plan = resolver().resolve(
                    safe_context(user_request=user_request),
                    AIUnderstandingProposal(
                        intent="mutate",
                        referenced_device_id="lamp_1",
                        capability_hint="power.switch",
                        raw_arguments=(("state", "true"),),
                    ),
                )

                self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
                self.assertEqual(plan.steps, ())

    def test_missing_required_state_resolves_clarify_missing_parameter(self):
        plan = resolver().resolve(
            safe_context(user_request="Cambia power.switch del dispositivo lamp_1."),
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

    def test_fabricated_capability_cannot_become_authority(self):
        plan = resolver().resolve(
            safe_context(user_request="Lee el estado de lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
                confidence=1.0,
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
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

    def test_refusal_precheck_refuses_destructive_request_without_proposal(self):
        plan = resolver().refusal_precheck(
            safe_context(user_request="Borra todos los dispositivos.")
        )

        self.assertEqual(plan.kind, PLAN_KIND_REFUSE)
        self.assertEqual(plan.refusal.reason_code, "forbidden_operation")
        self.assertEqual(plan.steps, ())

    def test_refusal_precheck_returns_none_for_normal_request(self):
        plan = resolver().refusal_precheck(
            safe_context(user_request="Lee el estado de lamp_1.")
        )

        self.assertIsNone(plan)

    def test_llm_clarify_hint_cannot_override_sufficient_context(self):
        plan = resolver().resolve(
            safe_context(user_request="Lee el estado de lamp_1."),
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
        with self.assertRaises(AIValidationError) as raised:
            resolver().resolve(
                safe_context(
                    user_request="Lee bad;capability de lamp_1.",
                    capabilities=(
                        AISafeCapability(
                            name="bad;capability",
                            kind="reading",
                            parameters=(),
                        ),
                    ),
                ),
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
                safe_context(
                    user_request=(
                        "Enciende power.switch del dispositivo lamp_1 "
                        "con state true mode rm fast."
                    )
                ),
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
                safe_context(
                    user_request=(
                        "Enciende power.switch del dispositivo lamp_1 "
                        "con state=true&&bad."
                    )
                ),
                AIUnderstandingProposal(
                    intent="mutate",
                    referenced_device_id="lamp_1",
                    capability_hint="power.switch",
                    raw_arguments=(("state", "true&&bad"),),
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


class RoomNarrowingResolverTests(unittest.TestCase):
    def test_one_light_in_room_resolves_execute_candidate(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz del cuarto.",
                include_second_lamp=False,
                rooms={"lamp_1": "cuarto"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_one_light_unknown_room_never_executes(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz del garage.",
                include_second_lamp=False,
                rooms={"lamp_1": "cuarto"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_one_light_known_room_still_resolves_after_unknown_room_gate(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz del cuarto.",
                include_second_lamp=False,
                rooms={"lamp_1": "cuarto"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_one_light_without_room_language_preserves_previous_behavior(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz.",
                include_second_lamp=False,
                rooms={"lamp_1": "cuarto"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_two_known_rooms_with_unknown_requested_room_never_chooses_either(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz del garage.",
                include_second_lamp=True,
                rooms={"lamp_1": "cuarto", "lamp_2": "sala"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.clarification.candidate_options, ())

    def test_explicit_id_with_unmatched_location_clarifies(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Lee status.read de lamp_1 en el garage.",
                include_second_lamp=False,
                rooms={"lamp_1": "cuarto"},
            ),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
                operation_hint="read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_two_lights_same_room_clarifies(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz del cuarto.",
                include_second_lamp=True,
                rooms={"lamp_1": "cuarto", "lamp_2": "cuarto"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(
            plan.clarification.reason_code,
            "ambiguous_device",
        )

    def test_same_type_different_rooms_room_narrows_safely(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz del cuarto.",
                include_second_lamp=True,
                rooms={"lamp_1": "cuarto", "lamp_2": "sala"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")
        self.assertEqual(
            plan.steps[0].canonical_command_text,
            "device apply lamp_1 power.switch state=true",
        )

    def test_unknown_room_term_fails_closed(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz del patio.",
                include_second_lamp=True,
                rooms={"lamp_1": "cuarto", "lamp_2": "sala"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)

    def test_explicit_id_with_conflicting_room_clarifies(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Lee status.read de lamp_1 en el cuarto.",
                include_second_lamp=True,
                rooms={"lamp_1": "sala", "lamp_2": "cuarto"},
            ),
            AIUnderstandingProposal(
                intent="read",
                referenced_device_id="lamp_1",
                capability_hint="status.read",
                operation_hint="read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)

    def test_exact_display_name_with_conflicting_room_clarifies(self):
        context = AISafeContext(
            schema_version=PLAN_SCHEMA_VERSION,
            user_request="Lee el estado de la Velador del cuarto.",
            devices=(
                safe_device(
                    "lamp_1",
                    "Velador",
                    "light",
                    capabilities=default_capabilities(),
                    room="sala",
                ),
                safe_device(
                    "lamp_2",
                    "Estudio",
                    "light",
                    capabilities=default_capabilities(),
                    room="cuarto",
                ),
            ),
            command_grammar=(),
        )

        plan = resolver().resolve(
            context,
            AIUnderstandingProposal(
                intent="read",
                referenced_device_text="velador",
                capability_hint="status.read",
                operation_hint="read",
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)

    def test_no_room_mention_keeps_current_behavior(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz.",
                include_second_lamp=True,
                rooms={"lamp_1": "cuarto", "lamp_2": "sala"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)

    def test_room_matching_is_case_insensitive(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz de la Sala.",
                include_second_lamp=True,
                rooms={"lamp_1": "Sala", "lamp_2": "cuarto"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_room_matching_is_accent_insensitive(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz de la habitacion.",
                include_second_lamp=True,
                rooms={"lamp_1": "Habitación", "lamp_2": "Baño"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_habitacion_does_not_match_configured_cuarto(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz de la habitación.",
                include_second_lamp=True,
                rooms={"lamp_1": "cuarto", "lamp_2": "sala"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)

    def test_model_proposed_device_id_cannot_bypass_room_conflict(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende la luz del cuarto.",
                include_second_lamp=True,
                rooms={"lamp_1": "cuarto", "lamp_2": "sala"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_2",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_room_only_request_never_executes(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Enciende el cuarto.",
                include_second_lamp=True,
                rooms={"lamp_1": "cuarto", "lamp_2": "sala"},
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)


class ExactDisplayNameResolutionTests(unittest.TestCase):
    def test_exact_display_name_ignores_conflicting_room_never_other_device(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp near sala."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_exact_display_name_with_other_room_clarifies(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp in sala."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_exact_display_name_with_matching_room_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp in cuarto."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")
        self.assertEqual(
            plan.steps[0].canonical_command_text,
            "device apply lamp_1 power.switch state=true",
        )

    def test_exact_display_name_without_room_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_generic_phrase_with_room_still_narrows_to_other_device(self):
        plan = resolver().resolve(
            light_pair_context("Turn on the lamp in sala."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="lamp",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_2")

    def test_exact_other_display_name_with_mismatched_room_clarifies(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Floor Lamp in cuarto."),
            notify_mutation("Floor Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_exact_display_name_matching_is_case_insensitive(self):
        plan = resolver().resolve(
            light_pair_context("Turn on DESK LAMP."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_exact_display_name_matching_is_accent_insensitive(self):
        context = AISafeContext(
            schema_version=PLAN_SCHEMA_VERSION,
            user_request="Turn on the salon.",
            devices=(
                safe_device(
                    "lamp_1",
                    "Salón",
                    "light",
                    capabilities=default_capabilities(),
                    room="cuarto",
                ),
                safe_device(
                    "lamp_2",
                    "Cocina",
                    "light",
                    capabilities=default_capabilities(),
                    room="sala",
                ),
            ),
            command_grammar=(),
        )

        plan = resolver().resolve(
            context,
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="Salón",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_generic_class_display_name_does_not_hijack_generic_phrase(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Turn on the lamp.",
                include_second_lamp=True,
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="lamp",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.clarification.reason_code, "ambiguous_device")
        self.assertEqual(plan.clarification.candidate_options, ("lamp_1", "lamp_2"))

    def test_grounded_device_id_keeps_precedence_over_exact_display_name(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp lamp_1 near sala."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                referenced_device_text="Desk Lamp",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_prende_la_luz_del_cuarto_still_executes_room_light(self):
        plan = resolver().resolve(
            light_pair_context("Prende la luz del cuarto."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_apaga_lamp_2_still_executes_explicit_device(self):
        plan = resolver().resolve(
            light_pair_context("Apaga lamp_2."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_2",
                capability_hint="power.switch",
                raw_arguments=(("state", "false"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_2")

    def test_unlock_door_never_executes(self):
        plan = resolver().resolve(
            lock_context("Unlock door_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="door_1",
                capability_hint="lock.set",
                raw_arguments=(("state", "false"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_question_light_in_sala_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Is the light in the sala on?"),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="light",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_device_id_with_ambiguous_generic_text_still_clarifies(self):
        plan = resolver().resolve(
            safe_context(
                user_request="Turn on the lamp_1 lamp.",
                include_second_lamp=True,
            ),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                referenced_device_text="lamp",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_exact_display_name_with_unknown_location_fails_closed(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp near the patio."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())


class ExactDisplayIdentitySafetyTests(unittest.TestCase):
    def test_desk_lamp_backup_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp Backup."),
            notify_mutation("Desk Lamp Backup"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_desk_lamp_2_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp 2."),
            notify_mutation("Desk Lamp 2"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_desk_lampish_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lampish."),
            notify_mutation("Desk Lampish"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_partial_identity_needs_full_normalized_equality(self):
        for request, text in (
            ("Turn on Desk Lamp Backup.", "Desk Lamp Backup"),
            ("Turn on Desk Lamp 2.", "Desk Lamp 2"),
            ("Turn on Desk Lampish.", "Desk Lampish"),
        ):
            with self.subTest(request=request):
                plan = resolver().resolve(
                    light_pair_context(request),
                    notify_mutation(text),
                )

                self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
                self.assertEqual(plan.steps, ())

    def test_lowercase_referenced_text_is_case_insensitive_exact(self):
        plan = resolver().resolve(
            light_pair_context("TURN ON DESK LAMP."),
            notify_mutation("desk lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_referenced_text_without_accent_normalizes_to_display(self):
        plan = resolver().resolve(
            accent_pair_context("Turn on the salon."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="salon",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_device_id_precedence_unchanged(self):
        plan = resolver().resolve(
            light_pair_context("Turn on lamp_1."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_id="lamp_1",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_two_display_names_in_request_never_seize_single_device(self):
        plan = resolver().resolve(
            light_pair_context("Compare Desk Lamp with Floor Lamp."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_generic_lampara_room_narrowing_still_resolves(self):
        plan = resolver().resolve(
            light_pair_context("Enciende la lampara del cuarto."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="lampara",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")


class EntityBoundaryExactIdentityTests(unittest.TestCase):
    def test_truncated_span_backup_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp Backup."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_truncated_span_2_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp 2."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_truncated_span_pro_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp Pro."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_truncated_span_lampish_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lampish."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_truncated_span_fake_prefix_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Fake Desk Lamp."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_truncated_span_backup_with_full_text_also_clarifies(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp Backup."),
            notify_mutation("Desk Lamp Backup"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_clean_exact_display_name_still_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_clean_exact_display_name_with_room_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp in cuarto."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_clean_exact_display_name_other_room_clarifies(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp in sala."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_generic_lamp_in_sala_still_narrows(self):
        plan = resolver().resolve(
            light_pair_context("Turn on the lamp in sala."),
            AIUnderstandingProposal(
                intent="mutate",
                referenced_device_text="lamp",
                capability_hint="power.switch",
                raw_arguments=(("state", "true"),),
            ),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_2")

    def test_punctuation_preserves_clean_boundaries(self):
        for request in (
            "Turn on Desk Lamp.",
            "Turn on Desk Lamp, please",
            "Turn on Desk Lamp!",
            "Turn on Desk Lamp please",
        ):
            with self.subTest(request=request):
                plan = resolver().resolve(
                    light_pair_context(request),
                    notify_mutation("Desk Lamp"),
                )

                self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
                self.assertEqual(plan.steps[0].target_device_id, "lamp_1")

    def test_question_form_never_seizes_identity(self):
        plan = resolver().resolve(
            light_pair_context("Can you turn on Desk Lamp?"),
            notify_mutation("Desk Lamp"),
        )

        self.assertNotEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps, ())

    def test_request_without_article_before_display_still_executes(self):
        plan = resolver().resolve(
            light_pair_context("Enciende Desk Lamp."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_EXECUTE)
        self.assertEqual(plan.steps[0].target_device_id, "lamp_1")


class ConnectorBoundaryExactIdentityTests(unittest.TestCase):
    def test_connector_and_tail_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp and backup."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_connector_or_tail_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp or backup."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_connector_with_tail_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp with backup."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_connector_but_tail_never_executes(self):
        plan = resolver().resolve(
            light_pair_context("Turn on Desk Lamp but backup."),
            notify_mutation("Desk Lamp"),
        )

        self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
        self.assertEqual(plan.steps, ())

    def test_connector_after_second_display_clarifies(self):
        for request in (
            "Turn on Desk Lamp and Floor Lamp.",
            "Turn on Desk Lamp or Floor Lamp.",
            "Turn on Desk Lamp with Floor Lamp.",
            "Turn on Desk Lamp but Floor Lamp.",
            "Turn on Floor Lamp and Desk Lamp.",
        ):
            with self.subTest(request=request):
                plan = resolver().resolve(
                    light_pair_context(request),
                    notify_mutation("Desk Lamp"),
                )

                self.assertEqual(plan.kind, PLAN_KIND_CLARIFY)
                self.assertEqual(plan.steps, ())


def notify_mutation(device_text):
    return AIUnderstandingProposal(
        intent="mutate",
        referenced_device_text=device_text,
        capability_hint="power.switch",
        raw_arguments=(("state", "true"),),
    )


def light_pair_context(user_request):
    return AISafeContext(
        schema_version=PLAN_SCHEMA_VERSION,
        user_request=user_request,
        devices=(
            safe_device(
                "lamp_1",
                "Desk Lamp",
                "light",
                capabilities=default_capabilities(),
                room="cuarto",
            ),
            safe_device(
                "lamp_2",
                "Floor Lamp",
                "light",
                capabilities=default_capabilities(),
                room="sala",
            ),
        ),
        command_grammar=(),
    )


def accent_pair_context(user_request):
    return AISafeContext(
        schema_version=PLAN_SCHEMA_VERSION,
        user_request=user_request,
        devices=(
            safe_device(
                "lamp_1",
                "Salón",
                "light",
                capabilities=default_capabilities(),
                room="cuarto",
            ),
            safe_device(
                "lamp_2",
                "Cocina",
                "light",
                capabilities=default_capabilities(),
                room="sala",
            ),
        ),
        command_grammar=(),
    )


def lock_context(user_request):
    return AISafeContext(
        schema_version=PLAN_SCHEMA_VERSION,
        user_request=user_request,
        devices=(
            safe_device(
                "door_1",
                "Main Door",
                "lock",
                capabilities=(
                    AISafeCapability(name="status.read", kind="reading", parameters=()),
                    AISafeCapability(
                        name="lock.set",
                        kind="action",
                        parameters=(
                            (
                                ("name", "state"),
                                ("required", True),
                                ("type", "boolean"),
                            ),
                        ),
                    ),
                ),
                room="entrada",
            ),
        ),
        command_grammar=(),
    )


def resolver():
    return DeterministicUnderstandingResolver()


def safe_context(
    *,
    user_request="Lee el estado de lamp_1.",
    include_second_lamp=False,
    capabilities=None,
    rooms=None,
):
    rooms = rooms or {}
    devices = [
        safe_device(
            "lamp_1",
            "Lamp",
            "light",
            capabilities=capabilities or default_capabilities(),
            room=rooms.get("lamp_1"),
        )
    ]
    if include_second_lamp:
        devices.append(
            safe_device(
                "lamp_2",
                "Desk Lamp",
                "light",
                capabilities=default_capabilities(),
                room=rooms.get("lamp_2"),
            )
        )
    return AISafeContext(
        schema_version=PLAN_SCHEMA_VERSION,
        user_request=user_request,
        devices=tuple(devices),
        command_grammar=(),
    )


def safe_device(device_id, display_name, device_type, *, capabilities, room=None):
    return AISafeDevice(
        device_id=device_id,
        display_name=display_name,
        device_type=device_type,
        capabilities=tuple(capabilities),
        state=AISafeDeviceState(status="known", semantic_properties=(("power", False),)),
        room=room,
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
