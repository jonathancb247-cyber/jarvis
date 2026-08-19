import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from jarvis_core.voice.provider_contracts import (
    FixtureCategory,
    ProviderFailureCategory,
    STTFixture,
    TTSPhraseFixture,
)
from jarvis_core.voice.provider_reports import (
    ProviderBakeOffReport,
    ProviderRecommendation,
    validate_no_secret_markers,
)
from jarvis_core.voice.providers.groq_stt import (
    GROQ_STT_MODELS,
    GroqSTTConfig,
    GroqSTTProvider,
    GroqSTTResponse,
)
from jarvis_core.voice.providers.piper_tts import (
    PiperTTSConfig,
    PiperTTSProvider,
    PiperTTSRunResult,
    PiperTTSRunner,
)


class FakeGroqTransport:
    def __init__(self, response=None, error=None):
        self.response = response or GroqSTTResponse(200, {"text": "enciende la lampara"}, 28)
        self.error = error
        self.calls = []

    def transcribe(self, *, config, api_key, audio_path):
        self.calls.append((config, api_key, audio_path))
        if self.error is not None:
            raise self.error
        return self.response


class WritingPiperRunner(PiperTTSRunner):
    def __init__(self, returncode=0, write_valid_wav=True):
        self.returncode = returncode
        self.write_valid_wav = write_valid_wav
        self.calls = []

    def run(self, *, config, text, output_path):
        self.calls.append((config, text, output_path))
        if self.write_valid_wav:
            _write_wav(output_path)
        else:
            output_path.write_text("not wav", encoding="utf-8")
        return PiperTTSRunResult(self.returncode)


class GroqSTTAdapterTests(unittest.TestCase):
    def test_groq_adapter_uses_same_boundary_for_both_models(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = _audio_fixture(temp_dir)
            for model in GROQ_STT_MODELS:
                transport = FakeGroqTransport()
                provider = GroqSTTProvider(
                    GroqSTTConfig(model=model),
                    transport=transport,
                )
                with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_fake_for_tests"}, clear=False):
                    result = provider.evaluate_stt(_stt_fixture(audio))

                self.assertIsNone(result.failure)
                self.assertEqual(result.provider.version_or_model, model)
                self.assertEqual(result.final_transcript, "enciende la lampara")
                self.assertEqual(result.metrics["real_provider_values"], 1)
                self.assertEqual(transport.calls[0][1], "gsk_fake_for_tests")

    def test_groq_missing_credential_fails_safely(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = GroqSTTProvider(
                GroqSTTConfig(),
                transport=FakeGroqTransport(),
            )
            with patch.dict(os.environ, {}, clear=True):
                result = provider.evaluate_stt(_stt_fixture(_audio_fixture(temp_dir)))

        self.assertEqual(result.failure.category, ProviderFailureCategory.UNAVAILABLE)
        self.assertEqual(result.failure.safe_message, "missing_groq_api_key")

    def test_groq_timeout_and_quota_are_normalized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = _stt_fixture(_audio_fixture(temp_dir))
            with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_fake_for_tests"}, clear=False):
                timeout = GroqSTTProvider(
                    GroqSTTConfig(),
                    transport=FakeGroqTransport(error=TimeoutError()),
                ).evaluate_stt(fixture)
                quota = GroqSTTProvider(
                    GroqSTTConfig(),
                    transport=FakeGroqTransport(
                        GroqSTTResponse(429, {"error": "not exposed"}, 24)
                    ),
                ).evaluate_stt(fixture)

        self.assertEqual(timeout.failure.category, ProviderFailureCategory.TIMEOUT)
        self.assertEqual(quota.failure.category, ProviderFailureCategory.QUOTA_OR_CAPACITY)
        self.assertNotIn("not exposed", quota.failure.safe_message)

    def test_groq_malformed_provider_response_is_normalized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = GroqSTTProvider(
                GroqSTTConfig(),
                transport=FakeGroqTransport(GroqSTTResponse(200, {"bad": "shape"}, 16)),
            )
            with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_fake_for_tests"}, clear=False):
                result = provider.evaluate_stt(_stt_fixture(_audio_fixture(temp_dir)))

        self.assertEqual(result.failure.category, ProviderFailureCategory.MALFORMED_OUTPUT)

    def test_groq_report_keeps_real_provider_mode_and_no_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = GroqSTTProvider(
                GroqSTTConfig(),
                transport=FakeGroqTransport(),
            )
            with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_fake_for_tests"}, clear=False):
                result = provider.evaluate_stt(_stt_fixture(_audio_fixture(temp_dir)))

        report = ProviderBakeOffReport(
            provider=provider.identity,
            fixture_set="voice-phase-2b-local-files",
            stt_results=(result,),
            recommendation=ProviderRecommendation.CONTINUE,
            synthetic_only=False,
        )
        payload = report.as_dict()

        self.assertEqual(payload["evaluation_mode"], "real_provider")
        self.assertFalse(payload["synthetic_only"])
        self.assertTrue(payload["stt_metrics"][0]["real_provider_values"])
        self.assertEqual(validate_no_secret_markers(report), ())


class PiperTTSAdapterTests(unittest.TestCase):
    def test_piper_subprocess_uses_maintained_module_cli_without_shell(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe = Path(temp_dir) / "Local Python" / "python.exe"
            data_dir = Path(temp_dir) / "Voice Data"
            output = Path(temp_dir) / "out.wav"
            exe.parent.mkdir()
            data_dir.mkdir()
            exe.write_text("", encoding="utf-8")

            class Completed:
                returncode = 0

            with patch("subprocess.run", return_value=Completed()) as run:
                PiperTTSRunner().run(
                    config=PiperTTSConfig(
                        exe,
                        "es_MX-ald-medium",
                        data_dir,
                        Path(temp_dir),
                    ),
                    text="Voy a encender la lámpara. ¿Confirmas?",
                    output_path=output,
                )

        kwargs = run.call_args.kwargs
        args = run.call_args.args[0]
        self.assertIsInstance(args, list)
        self.assertEqual(
            args,
            [
                str(exe),
                "-m",
                "piper",
                "-m",
                "es_MX-ald-medium",
                "-f",
                str(output),
                "--data-dir",
                str(data_dir),
                "--",
                "Voy a encender la lámpara. ¿Confirmas?",
            ],
        )
        self.assertFalse(kwargs["shell"])
        self.assertNotIn("input", kwargs)

    def test_piper_missing_executable_data_dir_and_voice_fail_safely(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_exe = PiperTTSProvider(
                PiperTTSConfig(
                    Path(temp_dir) / "missing.exe",
                    "es_MX-ald-medium",
                    Path(temp_dir),
                    Path(temp_dir) / "out",
                ),
                runner=WritingPiperRunner(),
            ).evaluate_tts(_tts_fixture())
            exe = Path(temp_dir) / "python.exe"
            exe.write_text("", encoding="utf-8")
            missing_data_dir = PiperTTSProvider(
                PiperTTSConfig(
                    exe,
                    "es_MX-ald-medium",
                    Path(temp_dir) / "missing-data",
                    Path(temp_dir) / "out",
                ),
                runner=WritingPiperRunner(),
            ).evaluate_tts(_tts_fixture())
            data_dir = Path(temp_dir) / "voices"
            data_dir.mkdir()
            missing_voice = PiperTTSProvider(
                PiperTTSConfig(
                    exe,
                    "es_MX-ald-medium",
                    data_dir,
                    Path(temp_dir) / "out",
                ),
                runner=WritingPiperRunner(),
            ).evaluate_tts(_tts_fixture())

        self.assertEqual(missing_exe.failure.category, ProviderFailureCategory.UNAVAILABLE)
        self.assertEqual(missing_data_dir.failure.category, ProviderFailureCategory.INVALID_INPUT)
        self.assertEqual(missing_voice.failure.category, ProviderFailureCategory.INVALID_INPUT)

    def test_piper_valid_wav_result_records_real_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe, data_dir = _piper_files(temp_dir)
            runner = WritingPiperRunner()
            provider = PiperTTSProvider(
                PiperTTSConfig(
                    exe,
                    "es_MX-ald-medium",
                    data_dir,
                    Path(temp_dir) / "voice output",
                ),
                runner=runner,
            )
            result = provider.evaluate_tts(_tts_fixture("tts confirmation"))

        self.assertIsNone(result.failure)
        self.assertEqual(result.provider.version_or_model, "es_MX-ald-medium")
        self.assertTrue(result.synthesized_output_reference.endswith("tts_confirmation.wav"))
        self.assertEqual(result.metrics["real_provider_values"], 1)
        self.assertEqual(result.metrics["wav_valid"], 1)
        self.assertGreaterEqual(result.metrics["generated_audio_duration_ms"], 0)
        self.assertEqual(runner.calls[0][1], "Listo.")

    def test_piper_invalid_wav_and_synthesis_failure_are_normalized(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe, data_dir = _piper_files(temp_dir)
            invalid = PiperTTSProvider(
                PiperTTSConfig(
                    exe,
                    "es_MX-ald-medium",
                    data_dir,
                    Path(temp_dir) / "out-invalid",
                ),
                runner=WritingPiperRunner(write_valid_wav=False),
            ).evaluate_tts(_tts_fixture())
            failed = PiperTTSProvider(
                PiperTTSConfig(
                    exe,
                    "es_MX-ald-medium",
                    data_dir,
                    Path(temp_dir) / "out-failed",
                ),
                runner=WritingPiperRunner(returncode=2),
            ).evaluate_tts(_tts_fixture())

        self.assertEqual(invalid.failure.category, ProviderFailureCategory.MALFORMED_OUTPUT)
        self.assertEqual(failed.failure.category, ProviderFailureCategory.PROVIDER_ERROR)


def _stt_fixture(audio_path):
    return STTFixture(
        "stt_local_fixture",
        (
            FixtureCategory.MEXICAN_SPANISH,
            FixtureCategory.TECHNICAL_VOCABULARY,
        ),
        "enciende la lampara",
        audio_reference=str(audio_path),
    )


def _tts_fixture(fixture_id="tts_fixture"):
    return TTSPhraseFixture(
        fixture_id,
        (FixtureCategory.ACKNOWLEDGEMENT,),
        "Listo.",
    )


def _audio_fixture(temp_dir):
    audio = Path(temp_dir) / "sample.wav"
    _write_wav(audio)
    return audio


def _piper_files(temp_dir):
    exe = Path(temp_dir) / "Local Python" / "python.exe"
    data_dir = Path(temp_dir) / "Voice Data"
    exe.parent.mkdir()
    data_dir.mkdir()
    exe.write_text("", encoding="utf-8")
    (data_dir / "es_MX-ald-medium.onnx").write_text("", encoding="utf-8")
    (data_dir / "es_MX-ald-medium.onnx.json").write_text("", encoding="utf-8")
    return exe, data_dir


def _write_wav(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 160)


if __name__ == "__main__":
    unittest.main()
