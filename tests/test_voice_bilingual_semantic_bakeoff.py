import unittest

from jarvis_core.voice.provider_bakeoff import (
    build_bilingual_semantic_fixtures,
    build_mock_bakeoff_report,
    build_mock_provider_identity,
)
from jarvis_core.voice.semantic_bakeoff import (
    ConceptualTool,
    DownstreamSemanticOutput,
    SemanticOutcomeTag,
    compare_bilingual_pair,
    evaluate_downstream_semantics,
)


class BilingualSemanticFixtureTests(unittest.TestCase):
    def test_required_bilingual_pairs_are_present(self):
        fixtures = build_bilingual_semantic_fixtures()
        utterances = {fixture.utterance for fixture in fixtures}
        pair_languages = {}
        for fixture in fixtures:
            pair_languages.setdefault(fixture.pair_id, set()).add(fixture.language)

        self.assertIn("turn on the flashlight", utterances)
        self.assertIn("enciende la linterna", utterances)
        self.assertIn("open Wi-Fi settings", utterances)
        self.assertIn("abre los ajustes de Wi-Fi", utterances)
        self.assertIn("show Mexico City on the map", utterances)
        self.assertIn("muestrame Ciudad de Mexico en el mapa", utterances)
        self.assertIn("create a calendar event tomorrow at 5 PM", utterances)
        self.assertIn("crea un evento manana a las 5", utterances)
        self.assertEqual(len(pair_languages), 4)
        for languages in pair_languages.values():
            self.assertEqual(languages, {"en-US", "es-MX"})


class DownstreamSemanticEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.provider = build_mock_provider_identity()
        self.fixtures = {
            fixture.fixture_id: fixture for fixture in build_bilingual_semantic_fixtures()
        }

    def test_correct_transcript_wrong_tool_is_semantic_failure_not_stt_failure(self):
        fixture = self.fixtures["semantic_flashlight_es"]
        result = evaluate_downstream_semantics(
            self.provider,
            fixture,
            DownstreamSemanticOutput(
                transcript=fixture.utterance,
                intent=fixture.expectation.intent,
                tool=ConceptualTool.OPEN_SETTINGS,
                arguments=fixture.expectation.arguments,
            ),
        )

        self.assertEqual(result.scores.stt_transcription_accuracy, 1.0)
        self.assertEqual(result.scores.tool_selection_accuracy, 0.0)
        self.assertEqual(result.scores.end_to_end_task_success, 0.0)
        self.assertIn(
            SemanticOutcomeTag.SPANISH_TRANSCRIPT_PASS_TOOL_FAIL,
            result.outcome_tags,
        )

    def test_correct_tool_malformed_arguments_are_scored_separately(self):
        fixture = self.fixtures["semantic_wifi_settings_en"]
        result = evaluate_downstream_semantics(
            self.provider,
            fixture,
            DownstreamSemanticOutput(
                transcript=fixture.utterance,
                intent=fixture.expectation.intent,
                tool=fixture.expectation.tool,
                arguments={"panel": "bluetooth"},
            ),
        )

        self.assertEqual(result.scores.tool_selection_accuracy, 1.0)
        self.assertEqual(result.scores.argument_extraction_accuracy, 0.0)
        self.assertEqual(result.scores.end_to_end_task_success, 0.0)

    def test_relative_datetime_failure_is_visible(self):
        fixture = self.fixtures["semantic_calendar_tomorrow_5pm_en"]
        result = evaluate_downstream_semantics(
            self.provider,
            fixture,
            DownstreamSemanticOutput(
                transcript=fixture.utterance,
                intent=fixture.expectation.intent,
                tool=fixture.expectation.tool,
                arguments=fixture.expectation.arguments,
                relative_datetime=None,
            ),
        )

        self.assertEqual(result.scores.relative_datetime_normalization, 0.0)
        self.assertIn(
            SemanticOutcomeTag.RELATIVE_DATETIME_NOT_NORMALIZED,
            result.outcome_tags,
        )

    def test_machine_formatted_clarification_is_ux_failure(self):
        fixture = self.fixtures["semantic_calendar_tomorrow_5_es"]
        result = evaluate_downstream_semantics(
            self.provider,
            fixture,
            DownstreamSemanticOutput(
                transcript=fixture.utterance,
                intent=fixture.expectation.intent,
                tool=fixture.expectation.tool,
                arguments=fixture.expectation.arguments,
                relative_datetime=fixture.expectation.relative_datetime,
                clarification_requested=True,
                clarification_prompt="Please provide an ISO timestamp like 2026-08-31T17:00.",
            ),
        )

        self.assertEqual(result.scores.clarification_quality, 0.0)
        self.assertIn(
            SemanticOutcomeTag.MACHINE_FORMATTED_CLARIFICATION_REQUESTED,
            result.outcome_tags,
        )

    def test_necessary_clarification_passes_without_api_formatted_input(self):
        fixture = self.fixtures["semantic_calendar_tomorrow_5_es"]
        result = evaluate_downstream_semantics(
            self.provider,
            fixture,
            DownstreamSemanticOutput(
                transcript=fixture.utterance,
                intent=fixture.expectation.intent,
                tool=fixture.expectation.tool,
                arguments=fixture.expectation.arguments,
                relative_datetime=fixture.expectation.relative_datetime,
                clarification_requested=True,
                clarification_prompt="Debe ser a las 5 de la tarde o de la manana?",
            ),
        )

        self.assertEqual(result.scores.clarification_quality, 1.0)
        self.assertEqual(result.scores.end_to_end_task_success, 0.0)
        self.assertIn(SemanticOutcomeTag.CLARIFICATION_NEEDED, result.outcome_tags)

    def test_unnecessary_clarification_fails(self):
        fixture = self.fixtures["semantic_map_mexico_city_en"]
        result = evaluate_downstream_semantics(
            self.provider,
            fixture,
            DownstreamSemanticOutput(
                transcript=fixture.utterance,
                intent=fixture.expectation.intent,
                tool=fixture.expectation.tool,
                arguments=fixture.expectation.arguments,
                clarification_requested=True,
                clarification_prompt="Which app should I use?",
            ),
        )

        self.assertEqual(result.scores.clarification_quality, 0.0)
        self.assertIn(
            SemanticOutcomeTag.CLARIFICATION_UNNECESSARY,
            result.outcome_tags,
        )

    def test_english_pass_spanish_fail_is_represented_distinctly(self):
        english = self.fixtures["semantic_flashlight_en"]
        spanish = self.fixtures["semantic_flashlight_es"]
        english_result = evaluate_downstream_semantics(
            self.provider,
            english,
            DownstreamSemanticOutput(
                transcript=english.utterance,
                intent=english.expectation.intent,
                tool=english.expectation.tool,
                arguments=english.expectation.arguments,
            ),
        )
        spanish_result = evaluate_downstream_semantics(
            self.provider,
            spanish,
            DownstreamSemanticOutput(
                transcript=spanish.utterance,
                intent=spanish.expectation.intent,
                tool=ConceptualTool.SHOW_MAP,
                arguments=spanish.expectation.arguments,
            ),
        )

        self.assertEqual(
            compare_bilingual_pair((english_result, spanish_result)),
            (SemanticOutcomeTag.ENGLISH_PASS_SPANISH_FAIL,),
        )

    def test_mock_report_contains_semantic_tool_metrics(self):
        payload = build_mock_bakeoff_report().as_dict()

        self.assertEqual(len(payload["semantic_tool_metrics"]), 8)
        self.assertEqual(
            payload["semantic_tool_metrics"][0]["scores"][
                "stt_transcription_accuracy"
            ],
            1.0,
        )

    def test_conceptual_tools_do_not_execute(self):
        module = __import__(
            "jarvis_core.voice.semantic_bakeoff",
            fromlist=["semantic_bakeoff"],
        )
        names = set(vars(module))

        self.assertNotIn("Runtime", names)
        self.assertNotIn("Planner", names)
        self.assertNotIn("Command", names)
        self.assertNotIn("Driver", names)
        self.assertTrue(all(callable_tool.value for callable_tool in ConceptualTool))


if __name__ == "__main__":
    unittest.main()
