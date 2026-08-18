import unittest

from jarvis_core.voice.benchmark import (
    BENCHMARK_VERSION,
    IntentOutcome,
    VoiceBenchmarkRunner,
    build_phase1_scenarios,
)
from jarvis_core.voice.events import VoiceEvent, VoiceEventKind
from jarvis_core.voice.fakes import (
    FakeSTTAction,
    FakeSTTProvider,
    FakeSTTStep,
    FakeTTSAction,
    FakeTTSProvider,
    FakeTTSStep,
)
from jarvis_core.voice.session import ConversationSession, SessionState
from jarvis_core.voice.turns import TurnManager, TurnState


class FakeSTTProviderTests(unittest.TestCase):
    def test_fake_stt_emits_partial_and_final_events(self):
        provider = FakeSTTProvider(
            (
                FakeSTTStep(FakeSTTAction.PARTIAL, "enciende", 10, 0.4),
                FakeSTTStep(FakeSTTAction.FINAL, "enciende la lámpara", 30, 0.95),
            )
        )

        events = provider.events()

        self.assertEqual(events[0].kind, VoiceEventKind.STT_PARTIAL)
        self.assertEqual(events[0].transcript, "enciende")
        self.assertEqual(events[1].kind, VoiceEventKind.STT_FINAL)
        self.assertEqual(events[1].transcript, "enciende la lámpara")

    def test_fake_stt_empty_final_becomes_safe_error(self):
        events = FakeSTTProvider(
            (FakeSTTStep(FakeSTTAction.FINAL, "", 10),)
        ).events()

        self.assertEqual(events[0].kind, VoiceEventKind.STT_ERROR)
        self.assertEqual(events[0].note, "invalid_input")

    def test_fake_stt_timeout_and_cancel_are_provider_neutral(self):
        events = FakeSTTProvider(
            (
                FakeSTTStep(FakeSTTAction.TIMEOUT, simulated_time_ms=20),
                FakeSTTStep(FakeSTTAction.CANCEL, simulated_time_ms=30),
            )
        ).events()

        self.assertEqual([event.kind for event in events], [VoiceEventKind.STT_TIMEOUT, VoiceEventKind.STT_CANCELLED])
        self.assertEqual([event.note for event in events], ["timeout", "cancelled"])


class FakeTTSProviderTests(unittest.TestCase):
    def test_fake_tts_lifecycle_without_audio_generation(self):
        provider = FakeTTSProvider(
            (
                FakeTTSStep(FakeTTSAction.START, 10),
                FakeTTSStep(FakeTTSAction.FIRST_AUDIO, 30),
                FakeTTSStep(FakeTTSAction.COMPLETE, 80),
            )
        )

        events = provider.events("Listo.")

        self.assertEqual(
            [event.kind for event in events],
            [
                VoiceEventKind.TTS_STARTED,
                VoiceEventKind.TTS_FIRST_AUDIO,
                VoiceEventKind.TTS_COMPLETED,
            ],
        )

    def test_fake_tts_supports_interruption_and_error(self):
        interrupted = FakeTTSProvider(
            (
                FakeTTSStep(FakeTTSAction.START, 10),
                FakeTTSStep(FakeTTSAction.INTERRUPT, 25),
            )
        ).events("Explicación larga.")
        error = FakeTTSProvider((FakeTTSStep(FakeTTSAction.ERROR, 10),)).events("Texto")

        self.assertEqual(interrupted[-1].kind, VoiceEventKind.TTS_INTERRUPTED)
        self.assertEqual(error[-1].kind, VoiceEventKind.TTS_ERROR)

    def test_fake_tts_rejects_empty_text(self):
        events = FakeTTSProvider((FakeTTSStep(FakeTTSAction.START, 10),)).events("")

        self.assertEqual(events[0].kind, VoiceEventKind.TTS_ERROR)
        self.assertEqual(events[0].note, "invalid_input")


class TurnManagerTests(unittest.TestCase):
    def test_partial_transcript_never_accepts_turn(self):
        manager = TurnManager()

        accepted = manager.handle(
            VoiceEvent(VoiceEventKind.STT_PARTIAL, transcript="enciende")
        )

        self.assertIsNone(accepted)
        self.assertEqual(manager.partial_transcripts_seen, 1)
        self.assertEqual(manager.final_transcripts_accepted, 0)

    def test_final_transcript_accepts_turn(self):
        manager = TurnManager()

        accepted = manager.handle(
            VoiceEvent(VoiceEventKind.STT_FINAL, transcript="enciende la lámpara")
        )

        self.assertIsNotNone(accepted)
        self.assertEqual(accepted.kind, VoiceEventKind.TURN_ACCEPTED)
        self.assertEqual(manager.state, TurnState.ENGAGED)

    def test_tts_interruption_changes_state(self):
        manager = TurnManager()

        manager.handle(VoiceEvent(VoiceEventKind.TTS_STARTED))
        manager.handle(VoiceEvent(VoiceEventKind.TTS_INTERRUPTED))

        self.assertEqual(manager.state, TurnState.INTERRUPTED)


class ConversationSessionTests(unittest.TestCase):
    def test_session_resolves_bounded_follow_up_reference(self):
        session = ConversationSession()
        session.start()
        session.set_reference("la lámpara")

        self.assertEqual(session.resolve_reference("apágala"), "la lámpara")

    def test_session_expiry_clears_reference_and_confirmation(self):
        session = ConversationSession()
        session.start()
        session.set_reference("la lámpara")
        session.set_pending_confirmation("pending-1")

        session.expire()

        self.assertEqual(session.state, SessionState.EXPIRED)
        self.assertIsNone(session.reference)
        self.assertIsNone(session.pending_confirmation_id)

    def test_session_reset_does_not_restore_persistent_memory(self):
        session = ConversationSession()
        session.start()
        session.remember_turn("enciende la lámpara")

        session.reset()

        self.assertEqual(session.state, SessionState.INACTIVE)
        self.assertEqual(session.turns, [])
        self.assertEqual(session.persisted_transcripts, [])

    def test_confirmation_reference_can_be_rejected_without_execution(self):
        session = ConversationSession()
        session.set_pending_confirmation("pending-1")

        rejected = session.reject_confirmation()

        self.assertEqual(rejected, "pending-1")
        self.assertIsNone(session.pending_confirmation_id)
        self.assertEqual(session.state, SessionState.ACTIVE)


class VoiceBenchmarkRunnerTests(unittest.TestCase):
    def test_phase1_scenarios_pass_with_fake_providers_only(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()

        self.assertTrue(report.passed)
        self.assertEqual(report.benchmark_version, BENCHMARK_VERSION)
        self.assertGreaterEqual(len(report.scenarios), 17)
        self.assertEqual(report.task_success_rate, 1.0)

    def test_report_format_is_compact_and_deterministic(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()

        payload = report.as_dict()

        self.assertEqual(payload["benchmark_version"], BENCHMARK_VERSION)
        self.assertIn("task_success_rate", payload)
        first = payload["scenarios"][0]
        self.assertIn("scenario_id", first)
        self.assertIn("simulated_metrics", first)
        self.assertIn("safety_violations", first)

    def test_every_latency_metric_is_labeled_simulated(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()

        for scenario in report.scenarios:
            with self.subTest(scenario=scenario.scenario_id):
                self.assertEqual(scenario.simulated_metrics["latency_kind"], "simulated")
                self.assertIn("simulated_endpoint_to_final_latency_ms", scenario.simulated_metrics)
                self.assertIn("simulated_response_to_first_audio_latency_ms", scenario.simulated_metrics)

    def test_safety_invariants_have_no_violations(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()

        for scenario in report.scenarios:
            with self.subTest(scenario=scenario.scenario_id):
                self.assertEqual(scenario.safety_violations, ())

    def test_partial_transcript_safety_scenario_does_not_execute_partial(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()
        scenario = _scenario(report, "partial_safety")

        self.assertEqual(scenario.simulated_metrics["partial_transcript_safety"], 1)
        self.assertIn("stt_partial", scenario.actual_transitions)
        self.assertIn("turn_accepted", scenario.actual_transitions)
        self.assertEqual(scenario.safety_violations, ())

    def test_unrelated_si_does_not_confirm(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()
        scenario = _scenario(report, "unrelated_si")

        self.assertNotIn("confirmation_pending", scenario.actual_transitions)
        self.assertNotIn("confirmation_bypass", scenario.safety_violations)

    def test_human_facing_device_name_scenario_does_not_speak_internal_id(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()
        scenario = _scenario(report, "human_name")

        self.assertEqual(scenario.safety_violations, ())
        self.assertNotIn("internal_id_spoken", scenario.safety_violations)

    def test_stt_failure_and_timeout_do_not_create_intent_or_state_mutation(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()

        for scenario_id in ("stt_failure", "provider_timeout"):
            scenario = _scenario(report, scenario_id)
            with self.subTest(scenario=scenario_id):
                self.assertTrue(scenario.passed)
                self.assertNotIn("turn_accepted", scenario.actual_transitions)
                self.assertNotIn("device_state_mutated_by_voice_failure", scenario.safety_violations)

    def test_confirmation_scenario_stops_at_pending_reference_without_mutation(self):
        report = VoiceBenchmarkRunner(build_phase1_scenarios()).run()
        scenario = _scenario(report, "no_physical_mutation")

        self.assertIn("confirmation_pending", scenario.actual_transitions)
        self.assertNotIn("physical_mutation_attempted", scenario.safety_violations)
        self.assertNotIn("real_driver_reached", scenario.safety_violations)


def _scenario(report, scenario_id):
    for scenario in report.scenarios:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise AssertionError(f"Missing scenario {scenario_id}")


if __name__ == "__main__":
    unittest.main()
