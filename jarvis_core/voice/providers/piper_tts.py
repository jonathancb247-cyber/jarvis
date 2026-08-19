"""Piper-style TTS adapter for opt-in Voice Phase 2B file evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import time
import wave

from ..provider_contracts import (
    HumanRating,
    ProviderDeployment,
    ProviderFailure,
    ProviderFailureCategory,
    ProviderIdentity,
    TTSCapabilities,
    TTSEvaluationResult,
    TTSPhraseFixture,
)


@dataclass(frozen=True)
class PiperTTSConfig:
    executable_path: Path
    voice_model_id: str
    data_dir: Path
    output_dir: Path
    timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.voice_model_id.strip():
            raise ValueError("voice_model_id is required")


@dataclass(frozen=True)
class PiperTTSRunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class PiperTTSRunner:
    def run(
        self,
        *,
        config: PiperTTSConfig,
        text: str,
        output_path: Path,
    ) -> PiperTTSRunResult:
        completed = subprocess.run(
            [
                str(config.executable_path),
                "-m",
                "piper",
                "-m",
                config.voice_model_id,
                "-f",
                str(output_path),
                "--data-dir",
                str(config.data_dir),
                "--",
                text,
            ],
            capture_output=True,
            timeout=config.timeout_seconds,
            check=False,
            shell=False,
        )
        return PiperTTSRunResult(completed.returncode)


@dataclass(frozen=True)
class PiperTTSProvider:
    config: PiperTTSConfig
    runner: PiperTTSRunner = PiperTTSRunner()

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            "piper",
            "tts",
            ProviderDeployment.LOCAL,
            self.config.voice_model_id,
        )

    @property
    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(
            batch=True,
            streaming=False,
            interruption=False,
            styles=False,
            prosody_controls=False,
            ssml_or_equivalent=False,
            local_offline=True,
        )

    def evaluate_tts(self, fixture: TTSPhraseFixture) -> TTSEvaluationResult:
        started = time.perf_counter()
        failure = self._preflight_failure(fixture)
        if failure is not None:
            return self._failure_result(fixture, failure)

        output_path = self._output_path(fixture)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            result = self.runner.run(
                config=self.config,
                text=fixture.text,
                output_path=output_path,
            )
        except subprocess.TimeoutExpired:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.TIMEOUT),
                latency_ms=_elapsed_ms(started),
            )
        except OSError:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.UNAVAILABLE),
                latency_ms=_elapsed_ms(started),
            )
        except Exception:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.PROVIDER_ERROR),
                latency_ms=_elapsed_ms(started),
            )

        latency_ms = _elapsed_ms(started)
        if result.returncode != 0:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.PROVIDER_ERROR),
                latency_ms=latency_ms,
            )
        duration_ms = _wav_duration_ms(output_path)
        if duration_ms is None:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.MALFORMED_OUTPUT),
                latency_ms=latency_ms,
            )

        return TTSEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            synthesized_output_reference=str(output_path),
            first_audio_ms=latency_ms,
            total_synthesis_ms=latency_ms,
            metrics={
                "real_provider_values": 1,
                "file_pipeline_synthesis_ms": latency_ms,
                "wav_valid": 1,
                "generated_audio_duration_ms": duration_ms,
            },
            human_rating=HumanRating(),
        )

    def _preflight_failure(self, fixture: TTSPhraseFixture) -> ProviderFailure | None:
        if not fixture.text.strip():
            return _failure(ProviderFailureCategory.INVALID_INPUT)
        if not self.config.executable_path.is_file():
            return _failure(ProviderFailureCategory.UNAVAILABLE)
        if not self.config.data_dir.is_dir():
            return _failure(ProviderFailureCategory.INVALID_INPUT)
        model_path = self.config.data_dir / f"{self.config.voice_model_id}.onnx"
        config_path = self.config.data_dir / f"{self.config.voice_model_id}.onnx.json"
        if not model_path.is_file() or not config_path.is_file():
            return _failure(ProviderFailureCategory.INVALID_INPUT)
        return None

    def _output_path(self, fixture: TTSPhraseFixture) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", fixture.fixture_id).strip("._")
        if not safe_id:
            safe_id = "tts_fixture"
        return self.config.output_dir / f"{safe_id}.wav"

    def _failure_result(
        self,
        fixture: TTSPhraseFixture,
        failure: ProviderFailure,
        *,
        latency_ms: int | None = None,
    ) -> TTSEvaluationResult:
        metrics: dict[str, int | float | str] = {"real_provider_values": 1}
        if latency_ms is not None:
            metrics["file_pipeline_synthesis_ms"] = latency_ms
        return TTSEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            failure=failure,
            first_audio_ms=latency_ms,
            total_synthesis_ms=latency_ms,
            metrics=metrics,
        )


def _wav_duration_ms(path: Path) -> int | None:
    try:
        with wave.open(str(path), "rb") as wav:
            frame_rate = wav.getframerate()
            frame_count = wav.getnframes()
            if frame_rate <= 0:
                return None
            return int(frame_count / frame_rate * 1000)
    except (OSError, wave.Error, EOFError):
        return None


def _failure(category: ProviderFailureCategory) -> ProviderFailure:
    return ProviderFailure(category, category.value)


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
