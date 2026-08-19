"""Groq STT adapter for opt-in Voice Phase 2B file evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import mimetypes
import os
from pathlib import Path
import re
import ssl
import time
from typing import Mapping, Protocol
from uuid import uuid4

from ..provider_contracts import (
    FixtureCategory,
    ProviderDeployment,
    ProviderFailure,
    ProviderFailureCategory,
    ProviderIdentity,
    STTCapabilities,
    STTEvaluationResult,
    STTFixture,
)


GROQ_STT_MODELS = ("whisper-large-v3-turbo", "whisper-large-v3")
_GROQ_HOST = "api.groq.com"
_GROQ_TRANSCRIPTION_PATH = "/openai/v1/audio/transcriptions"
_USER_AGENT = "JarvisOS/voice-eval"
_SUPPORTED_AUDIO_EXTENSIONS = {
    ".flac",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".ogg",
    ".wav",
    ".webm",
}


@dataclass(frozen=True)
class GroqSTTConfig:
    model: str = "whisper-large-v3-turbo"
    timeout_seconds: int = 30
    maximum_audio_bytes: int = 25 * 1024 * 1024
    maximum_response_bytes: int = 256 * 1024
    language: str = "es"

    def __post_init__(self) -> None:
        if self.model not in GROQ_STT_MODELS:
            raise ValueError("unsupported Groq STT model")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.maximum_audio_bytes <= 0:
            raise ValueError("maximum_audio_bytes must be positive")
        if self.maximum_response_bytes <= 0:
            raise ValueError("maximum_response_bytes must be positive")
        if not self.language.strip():
            raise ValueError("language is required")


@dataclass(frozen=True)
class GroqSTTResponse:
    status_code: int
    payload: Mapping[str, object] | None
    response_bytes: int


class GroqSTTTransport(Protocol):
    def transcribe(
        self,
        *,
        config: GroqSTTConfig,
        api_key: str,
        audio_path: Path,
    ) -> GroqSTTResponse:
        ...


class StdlibGroqSTTTransport:
    """Synchronous HTTPS multipart transport for Groq audio transcription."""

    def transcribe(
        self,
        *,
        config: GroqSTTConfig,
        api_key: str,
        audio_path: Path,
    ) -> GroqSTTResponse:
        body, content_type = _build_multipart_body(config, audio_path)
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(
            _GROQ_HOST,
            timeout=config.timeout_seconds,
            context=context,
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }
        try:
            conn.request("POST", _GROQ_TRANSCRIPTION_PATH, body=body, headers=headers)
            response = conn.getresponse()
            data = response.read(config.maximum_response_bytes + 1)
        finally:
            conn.close()
        if len(data) > config.maximum_response_bytes:
            return GroqSTTResponse(413, None, len(data))
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        return GroqSTTResponse(response.status, payload, len(data))


@dataclass(frozen=True)
class GroqSTTProvider:
    config: GroqSTTConfig
    transport: GroqSTTTransport = StdlibGroqSTTTransport()
    api_key_env: str = "GROQ_API_KEY"

    @property
    def identity(self) -> ProviderIdentity:
        return ProviderIdentity(
            "groq",
            "stt",
            ProviderDeployment.CLOUD,
            self.config.model,
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
            local_offline=False,
        )

    def evaluate_stt(self, fixture: STTFixture) -> STTEvaluationResult:
        started = time.perf_counter()
        audio_path = _validated_audio_path(fixture, self.config)
        if isinstance(audio_path, ProviderFailure):
            return self._failure_result(fixture, audio_path)

        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            return self._failure_result(
                fixture,
                ProviderFailure(
                    ProviderFailureCategory.UNAVAILABLE,
                    "missing_groq_api_key",
                ),
            )
        if "\n" in api_key or "\r" in api_key:
            return self._failure_result(
                fixture,
                ProviderFailure(
                    ProviderFailureCategory.INVALID_INPUT,
                    "invalid_groq_api_key",
                ),
            )

        try:
            response = self.transport.transcribe(
                config=self.config,
                api_key=api_key,
                audio_path=audio_path,
            )
        except TimeoutError:
            return self._failure_result(fixture, _failure(ProviderFailureCategory.TIMEOUT))
        except OSError:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.UNAVAILABLE),
            )
        except Exception:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.PROVIDER_ERROR),
            )

        latency_ms = _elapsed_ms(started)
        if response.status_code < 200 or response.status_code >= 300:
            return self._failure_result(
                fixture,
                _failure(_category_from_status(response.status_code)),
                latency_ms=latency_ms,
                response_bytes=response.response_bytes,
            )
        if response.payload is None:
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.MALFORMED_OUTPUT),
                latency_ms=latency_ms,
                response_bytes=response.response_bytes,
            )
        text = response.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return self._failure_result(
                fixture,
                _failure(ProviderFailureCategory.MALFORMED_OUTPUT),
                latency_ms=latency_ms,
                response_bytes=response.response_bytes,
            )

        metrics = _stt_metrics(fixture.expected_transcript, text)
        metrics.update(
            {
                "real_provider_values": 1,
                "provider_file_pipeline_latency_ms": latency_ms,
                "response_bytes": response.response_bytes,
            }
        )
        return STTEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            final_transcript=text,
            detected_language=fixture.language_hint,
            transcript_latency_ms=latency_ms,
            metrics=metrics,
        )

    def _failure_result(
        self,
        fixture: STTFixture,
        failure: ProviderFailure,
        *,
        latency_ms: int | None = None,
        response_bytes: int | None = None,
    ) -> STTEvaluationResult:
        metrics: dict[str, int | float | str] = {"real_provider_values": 1}
        if latency_ms is not None:
            metrics["provider_file_pipeline_latency_ms"] = latency_ms
        if response_bytes is not None:
            metrics["response_bytes"] = response_bytes
        return STTEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            failure=failure,
            transcript_latency_ms=latency_ms,
            metrics=metrics,
        )


def _validated_audio_path(
    fixture: STTFixture,
    config: GroqSTTConfig,
) -> Path | ProviderFailure:
    if not fixture.audio_reference:
        return _failure(ProviderFailureCategory.INVALID_INPUT)
    path = Path(fixture.audio_reference)
    if not path.is_file():
        return _failure(ProviderFailureCategory.INVALID_INPUT)
    if path.suffix.lower() not in _SUPPORTED_AUDIO_EXTENSIONS:
        return _failure(ProviderFailureCategory.UNSUPPORTED_LANGUAGE)
    if path.stat().st_size > config.maximum_audio_bytes:
        return _failure(ProviderFailureCategory.INVALID_INPUT)
    return path


def _build_multipart_body(config: GroqSTTConfig, audio_path: Path) -> tuple[bytes, str]:
    boundary = f"jarvisos-{uuid4().hex}"
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    parts: list[bytes] = []
    fields = {
        "model": config.model,
        "response_format": "json",
        "language": config.language,
        "temperature": "0",
    }
    for name, value in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8")
    parts.append(file_header)
    parts.append(audio_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _category_from_status(status_code: int) -> ProviderFailureCategory:
    if status_code == 408:
        return ProviderFailureCategory.TIMEOUT
    if status_code == 400:
        return ProviderFailureCategory.INVALID_INPUT
    if status_code == 413:
        return ProviderFailureCategory.INVALID_INPUT
    if status_code == 429:
        return ProviderFailureCategory.QUOTA_OR_CAPACITY
    if status_code >= 500:
        return ProviderFailureCategory.UNAVAILABLE
    return ProviderFailureCategory.PROVIDER_ERROR


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
