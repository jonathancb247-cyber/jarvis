"""whisper.cpp STT adapter for opt-in local Voice Phase 2B file evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import time

from ..provider_contracts import (
    ProviderDeployment,
    ProviderFailure,
    ProviderFailureCategory,
    ProviderIdentity,
    STTCapabilities,
    STTEvaluationResult,
    STTFixture,
)


_SUPPORTED_AUDIO_EXTENSIONS = {".wav"}


@dataclass(frozen=True)
class WhisperCppSTTConfig:
    executable_path: Path
    model_path: Path
    language: str = "es"
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not self.language.strip():
            raise ValueError("language is required")


@dataclass(frozen=True)
class WhisperCppSTTRunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class WhisperCppSTTRunner:
    def run(
        self,
        *,
        config: WhisperCppSTTConfig,
        audio_path: Path,
    ) -> WhisperCppSTTRunResult:
        completed = subprocess.run(
            [
                str(config.executable_path),
                "-m",
                str(config.model_path),
                "-f",
                str(audio_path),
                "-l",
                config.language,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.timeout_seconds,
            check=False,
            shell=False,
        )
        return WhisperCppSTTRunResult(
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )


@dataclass(frozen=True)
class WhisperCppSTTProvider:
    config: WhisperCppSTTConfig
    runner: WhisperCppSTTRunner = WhisperCppSTTRunner()

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            "whisper.cpp",
            "stt",
            ProviderDeployment.LOCAL,
            self.config.model_path.name,
        )

    @property
    def capabilities(self) -> STTCapabilities:
        return STTCapabilities(
            batch=True,
            streaming=False,
            partial_results=False,
            language_detection=False,
            timestamps=False,
            confidence=False,
            vocabulary_hints=False,
            cancellation=False,
            local_offline=True,
        )

    def evaluate_stt(self, fixture: STTFixture) -> STTEvaluationResult:
        started = time.perf_counter()
        failure = self._preflight_failure(fixture)
        if failure is not None:
            return self._failure_result(fixture, failure)

        audio_path = Path(fixture.audio_reference or "")
        try:
            result = self.runner.run(config=self.config, audio_path=audio_path)
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

        transcript = _extract_transcript(result.stdout)
        if not transcript:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.MALFORMED_OUTPUT),
                latency_ms=latency_ms,
            )

        metrics = _stt_metrics(fixture.expected_transcript, transcript)
        metrics.update(
            {
                "real_provider_values": 1,
                "provider_file_pipeline_latency_ms": latency_ms,
            }
        )
        return STTEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            final_transcript=transcript,
            detected_language=fixture.language_hint,
            transcript_latency_ms=latency_ms,
            metrics=metrics,
        )

    def _preflight_failure(self, fixture: STTFixture) -> ProviderFailure | None:
        if not fixture.audio_reference:
            return _failure(ProviderFailureCategory.INVALID_INPUT)
        audio_path = Path(fixture.audio_reference)
        if not audio_path.is_file():
            return _failure(ProviderFailureCategory.INVALID_INPUT)
        if audio_path.suffix.lower() not in _SUPPORTED_AUDIO_EXTENSIONS:
            return _failure(ProviderFailureCategory.INVALID_INPUT)
        if not self.config.executable_path.is_file():
            return _failure(ProviderFailureCategory.UNAVAILABLE)
        if not self.config.model_path.is_file():
            return _failure(ProviderFailureCategory.INVALID_INPUT)
        return None

    def _failure_result(
        self,
        fixture: STTFixture,
        failure: ProviderFailure,
        *,
        latency_ms: int | None = None,
    ) -> STTEvaluationResult:
        metrics: dict[str, int | float | str] = {"real_provider_values": 1}
        if latency_ms is not None:
            metrics["provider_file_pipeline_latency_ms"] = latency_ms
        return STTEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            failure=failure,
            transcript_latency_ms=latency_ms,
            metrics=metrics,
        )


def _extract_transcript(stdout: str) -> str:
    lines: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _looks_like_whisper_log(line):
            continue
        line = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
        if line:
            lines.append(line)
    return " ".join(lines).strip()


def _looks_like_whisper_log(line: str) -> bool:
    lowered = line.lower()
    log_prefixes = (
        "whisper_",
        "ggml_",
        "main:",
        "system_info:",
        "warning:",
        "error:",
    )
    return lowered.startswith(log_prefixes)


def _failure(category: ProviderFailureCategory) -> ProviderFailure:
    return ProviderFailure(category, category.value)


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _stt_metrics(expected: str, actual: str) -> dict[str, int | float | str]:
    expected_words = _words(expected)
    actual_words = _words(actual)
    distance = _levenshtein(expected_words, actual_words)
    wer = 0.0 if not expected_words else distance / len(expected_words)
    return {
        "wer": round(wer, 4),
        "technical_term_accuracy": _technical_term_accuracy(expected, actual),
        "code_switch_handling": _code_switch_handling(expected, actual),
    }


def _words(text: str) -> list[str]:
    normalized = text.lower().replace("-", " ")
    return re.findall(r"[a-z0-9áéíóúñü]+", normalized)


def _levenshtein(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for index, left_word in enumerate(left, start=1):
        current = [index]
        for right_index, right_word in enumerate(right, start=1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_word != right_word),
                )
            )
        previous = current
    return previous[-1]


def _technical_term_accuracy(expected: str, actual: str) -> float:
    terms = [
        term
        for term in ("esp32", "stm32", "mqtt", "obd")
        if term in expected.lower().replace("-", "")
    ]
    if not terms:
        return 1.0
    haystack = actual.lower().replace("-", "")
    hits = sum(1 for term in terms if term in haystack)
    return round(hits / len(terms), 4)


def _code_switch_handling(expected: str, actual: str) -> float:
    if not any(ord(char) < 128 and char.isalpha() for char in expected):
        return 1.0
    return 1.0 if actual.strip() else 0.0
