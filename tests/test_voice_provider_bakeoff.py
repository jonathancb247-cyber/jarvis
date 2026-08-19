import unittest

from jarvis_core.voice import VoiceBenchmarkRunner, build_phase1_scenarios
from jarvis_core.voice.provider_bakeoff import (
    MockSTTProvider,
    MockTTSProvider,
    build_default_stt_fixtures,
    build_default_tts_fixtures,
    build_mock_bakeoff_report,
    build_mock_provider_identity,
)
from jarvis_core.voice.provider_contracts import (
    FixtureCategory,
    HumanRating,
    ProviderDeployment,
    ProviderFailure,
    ProviderFailureCategory,
    ProviderIdentity,
    STTCapabilities,
    STTEvaluationResult,
    STTFixture,
    TTSCapabilities,
    TTSEvaluationResult,
    TTSPhraseFixture,
    normalize_provider_exception,
)
from jarvis_core.voice.provider_reports import (
    ProviderBakeOffReport,
    ProviderRecommendation,
    validate_no_secret_markers,
)


class ProviderContractTests(unittest.TestCase):
    def test_provider_identity_requires_name_and_mode(self):
        with self.assertRaises(ValueError):
            ProviderIdentity("", "mock", ProviderDeployment.LOCAL)
        with self.assertRaises(ValueError):
            ProviderIdentity("mock", "", ProviderDeployment.LOCAL)

    def test_capability_metadata_is_compact_and_not_registry(self):
        stt = STTCapabilities(
            streaming=True,
            partial_results=True,
            language_detection=True,
            timestamps=True,
            confidence=True,
            vocabulary_hints=True,
            cancellation=True,
            local_offline=True,
        )
        tts = TTSCapabilities(
            streaming=True,
            interruption=True,
            styles=True,
            prosody_controls=True,
            ssml_or_equivalent=True,
            local_offline=True,
        )

        self.assertTrue(stt.as_dict()["partial_results"])
        self.assertTrue(tts.as_dict()["interruption"])
        self.assertNotIn("registry", stt.as_dict())
        self.assertNotIn("provider_selection", tts.as_dict())

    def test_failure_categories_are_provider_neutral(self):
        expected = {
            "unavailable",
            "timeout",
            "cancelled",
            "unsupported_language",
            "invalid_input",
            "quota_or_capacity",
            "malformed_output",
            "provider_error",
        }

        self.assertEqual({item.value for item in ProviderFailureCategory}, expected)

    def test_raw_exception_is_normalized_without_leaking_repr(self):
        failure = normalize_provider_exception(RuntimeError("secret vendor detail"))

        self.assertEqual(failure.category, ProviderFailureCategory.PROVIDER_ERROR)
        self.assertEqual(failure.safe_message, "provider_error")
        self.assertNotIn("secret vendor detail", failure.safe_message)

    def test_human_rating_placeholders_validate_range(self):
        rating = HumanRating(naturalness=5, fatigue_annoyance=1)

        self.assertEqual(rating.naturalness, 5)
        with self.assertRaises(ValueError):
            HumanRating(naturalness=6)


class FixtureModelTests(unittest.TestCase):
    def test_default_stt_fixtures_cover_required_taxonomy(self):
        fixtures = build_default_stt_fixtures()
        categories = {category for fixture in fixtures for category in fixture.categories}

        self.assertIn(FixtureCategory.MEXICAN_SPANISH, categories)
        self.assertIn(FixtureCategory.CODE_SWITCHING, categories)
        self.assertIn(FixtureCategory.TECHNICAL_VOCABULARY, categories)
        self.assertIn(FixtureCategory.DEVICE_NAMES, categories)
        self.assertIn(FixtureCategory.ACRONYMS, categories)
        self.assertIn(FixtureCategory.HESITATION, categories)
        self.assertIn(FixtureCategory.SELF_CORRECTION, categories)
        self.assertIn(FixtureCategory.AMBIGUITY, categories)

    def test_default_tts_fixtures_cover_required_taxonomy(self):
        fixtures = build_default_tts_fixtures()
        categories = {category for fixture in fixtures for category in fixture.categories}

        self.assertIn(FixtureCategory.ACKNOWLEDGEMENT, categories)
        self.assertIn(FixtureCategory.CONFIRMATION, categories)
        self.assertIn(FixtureCategory.REFUSAL, categories)
        self.assertIn(FixtureCategory.WARNING, categories)
        self.assertIn(FixtureCategory.LONG_EXPLANATION, categories)
        self.assertIn(FixtureCategory.HUMAN_FACING_DEVICE_NAMES, categories)
        self.assertIn(FixtureCategory.BILINGUAL_TERMS, categories)

    def test_private_user_audio_fixture_is_rejected(self):
        with self.assertRaises(ValueError):
            STTFixture(
                "private",
                (FixtureCategory.MEXICAN_SPANISH,),
                "texto",
                private_user_audio=True,
            )

    def test_empty_tts_phrase_fixture_is_rejected(self):
        with self.assertRaises(ValueError):
            TTSPhraseFixture("empty", (FixtureCategory.ACKNOWLEDGEMENT,), "")


class MockProviderEvaluationTests(unittest.TestCase):
    def test_mock_stt_success_includes_partial_and_final_shape(self):
        provider = MockSTTProvider(
            build_mock_provider_identity(),
            STTCapabilities(partial_results=True, language_detection=True, confidence=True),
        )
        result = provider.evaluate_stt(build_default_stt_fixtures()[0])

        self.assertIsInstance(result, STTEvaluationResult)
        self.assertIsNone(result.failure)
        self.assertIsNotNone(result.final_transcript)
        self.assertEqual(len(result.partials), 1)
        self.assertEqual(result.detected_language, "es-MX")
        self.assertEqual(result.metrics["synthetic_test_values"], 1)

    def test_mock_stt_failure_paths(self):
        fixture = build_default_stt_fixtures()[0]
        for category in (
            ProviderFailureCategory.TIMEOUT,
            ProviderFailureCategory.UNAVAILABLE,
            ProviderFailureCategory.UNSUPPORTED_LANGUAGE,
            ProviderFailureCategory.QUOTA_OR_CAPACITY,
            ProviderFailureCategory.CANCELLED,
        ):
            provider = MockSTTProvider(
                build_mock_provider_identity(),
                STTCapabilities(),
                failure=ProviderFailure(category, category.value),
            )
            with self.subTest(category=category):
                result = provider.evaluate_stt(fixture)
                self.assertEqual(result.failure.category, category)
                self.assertIsNone(result.final_transcript)

    def test_mock_stt_malformed_output_is_normalized(self):
        result = MockSTTProvider(
            build_mock_provider_identity(),
            STTCapabilities(),
            malformed=True,
        ).evaluate_stt(build_default_stt_fixtures()[0])

        self.assertEqual(result.failure.category, ProviderFailureCategory.MALFORMED_OUTPUT)

    def test_mock_tts_success_includes_timing_and_rating_placeholders(self):
        provider = MockTTSProvider(
            build_mock_provider_identity(),
            TTSCapabilities(interruption=True, styles=True),
        )
        result = provider.evaluate_tts(build_default_tts_fixtures()[0])

        self.assertIsInstance(result, TTSEvaluationResult)
        self.assertIsNone(result.failure)
        self.assertEqual(result.first_audio_ms, 30)
        self.assertEqual(result.total_synthesis_ms, 95)
        self.assertIsNotNone(result.human_rating)
        self.assertEqual(result.metrics["synthetic_test_values"], 1)

    def test_mock_tts_failure_paths(self):
        fixture = build_default_tts_fixtures()[0]
        for category in (
            ProviderFailureCategory.TIMEOUT,
            ProviderFailureCategory.PROVIDER_ERROR,
            ProviderFailureCategory.CANCELLED,
            ProviderFailureCategory.UNAVAILABLE,
        ):
            provider = MockTTSProvider(
                build_mock_provider_identity(),
                TTSCapabilities(),
                failure=ProviderFailure(category, category.value),
            )
            with self.subTest(category=category):
                result = provider.evaluate_tts(fixture)
                self.assertEqual(result.failure.category, category)
                self.assertIsNone(result.synthesized_output_reference)

    def test_mock_tts_malformed_output_is_normalized(self):
        result = MockTTSProvider(
            build_mock_provider_identity(),
            TTSCapabilities(),
            malformed=True,
        ).evaluate_tts(build_default_tts_fixtures()[0])

        self.assertEqual(result.failure.category, ProviderFailureCategory.MALFORMED_OUTPUT)


class ProviderReportTests(unittest.TestCase):
    def test_mock_report_serializes_comparable_shape(self):
        report = build_mock_bakeoff_report()
        payload = report.as_dict()

        self.assertEqual(payload["provider_name"], "mock-provider")
        self.assertEqual(payload["provider_mode"], "mock")
        self.assertEqual(payload["local_or_cloud"], "local")
        self.assertEqual(payload["fixture_set"], "phase-2a-synthetic-fixtures")
        self.assertEqual(payload["recommendation"], ProviderRecommendation.CONTINUE.value)
        self.assertTrue(payload["synthetic_only"])
        self.assertGreater(len(payload["stt_metrics"]), 0)
        self.assertGreater(len(payload["tts_metrics"]), 0)
        self.assertIn("human_rating_summary", payload)

    def test_report_collects_normalized_failures(self):
        report = build_mock_bakeoff_report(
            stt_failure=ProviderFailure(
                ProviderFailureCategory.QUOTA_OR_CAPACITY,
                "quota_or_capacity",
            ),
            tts_failure=ProviderFailure(
                ProviderFailureCategory.TIMEOUT,
                "timeout",
            ),
        )

        self.assertIn(ProviderFailureCategory.QUOTA_OR_CAPACITY, report.normalized_failures())
        self.assertIn(ProviderFailureCategory.TIMEOUT, report.normalized_failures())

    def test_report_rejects_missing_fixture_set(self):
        with self.assertRaises(ValueError):
            ProviderBakeOffReport(
                provider=build_mock_provider_identity(),
                fixture_set="",
            )

    def test_privacy_report_contains_no_secret_markers_by_default(self):
        report = build_mock_bakeoff_report()

        self.assertEqual(validate_no_secret_markers(report), ())

    def test_privacy_helper_detects_secret_markers_without_exposing_values(self):
        report = ProviderBakeOffReport(
            provider=build_mock_provider_identity(),
            fixture_set="fixtures",
            privacy_notes=("contains api_key marker",),
        )

        self.assertEqual(validate_no_secret_markers(report), ("api_key",))


class ExistingVoiceBenchmarkRegressionTests(unittest.TestCase):
    def test_voice_phase1_benchmark_still_passes(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()

        self.assertTrue(report.passed)
        self.assertEqual(report.task_success_rate, 1.0)


if __name__ == "__main__":
    unittest.main()
