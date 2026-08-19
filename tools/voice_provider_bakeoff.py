"""Opt-in Voice Phase 2B real provider evaluation helper.

This is not a production JarvisOS CLI. It never captures microphone input,
plays speaker output or calls Runtime.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from jarvis_core.voice.provider_contracts import (
    FixtureCategory,
    ProviderDeployment,
    ProviderIdentity,
    STTFixture,
    TTSPhraseFixture,
)
from jarvis_core.voice.provider_reports import (
    ProviderBakeOffReport,
    ProviderRecommendation,
    validate_no_secret_markers,
)
from jarvis_core.voice.providers import (
    GROQ_STT_MODELS,
    GroqSTTConfig,
    GroqSTTProvider,
    PiperTTSConfig,
    PiperTTSProvider,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice provider bake-off helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    groq = subparsers.add_parser("groq-stt", help="Evaluate one Groq STT model")
    groq.add_argument("--audio", required=True)
    groq.add_argument("--expected", required=True)
    groq.add_argument("--fixture-id", default="local_stt_fixture")
    groq.add_argument("--model", choices=GROQ_STT_MODELS, default=GROQ_STT_MODELS[0])

    compare = subparsers.add_parser("groq-stt-compare", help="Compare both Groq STT models")
    compare.add_argument("--audio", required=True)
    compare.add_argument("--expected", required=True)
    compare.add_argument("--fixture-id", default="local_stt_fixture")

    piper = subparsers.add_parser("piper-tts", help="Evaluate local Piper TTS")
    piper.add_argument("--text", required=True)
    piper.add_argument("--fixture-id", default="local_tts_fixture")
    piper.add_argument("--piper", default=os.environ.get("PIPER_EXECUTABLE", ""))
    piper.add_argument("--voice", default=os.environ.get("PIPER_VOICE_MODEL", ""))
    piper.add_argument("--output-dir", default=os.environ.get("PIPER_OUTPUT_DIR", "voice-output.local"))

    args = parser.parse_args()
    if args.command == "groq-stt":
        report = _groq_report(args.audio, args.expected, args.fixture_id, (args.model,))
    elif args.command == "groq-stt-compare":
        report = _groq_report(args.audio, args.expected, args.fixture_id, GROQ_STT_MODELS)
    else:
        report = _piper_report(args.text, args.fixture_id, args.piper, args.voice, args.output_dir)

    if validate_no_secret_markers(report):
        raise SystemExit("report_contains_secret_marker")
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0


def _groq_report(
    audio: str,
    expected: str,
    fixture_id: str,
    models: tuple[str, ...],
) -> ProviderBakeOffReport:
    fixture = STTFixture(
        fixture_id,
        (
            FixtureCategory.MEXICAN_SPANISH,
            FixtureCategory.TECHNICAL_VOCABULARY,
        ),
        expected,
        audio_reference=audio,
    )
    results = tuple(
        GroqSTTProvider(GroqSTTConfig(model=model)).evaluate_stt(fixture)
        for model in models
    )
    return ProviderBakeOffReport(
        provider=ProviderIdentity("groq", "stt", ProviderDeployment.CLOUD, ",".join(models)),
        fixture_set="voice-phase-2b-local-files",
        stt_results=results,
        privacy_notes=("local fixture ids only", "no credential in report"),
        cost_quota_notes=("actual account limits are external to JarvisOS",),
        known_limitations=("file-pipeline latency only", "no live microphone evaluation"),
        recommendation=ProviderRecommendation.CONTINUE,
        synthetic_only=False,
    )


def _piper_report(
    text: str,
    fixture_id: str,
    executable: str,
    voice: str,
    output_dir: str,
) -> ProviderBakeOffReport:
    fixture = TTSPhraseFixture(
        fixture_id,
        (
            FixtureCategory.CONFIRMATION,
            FixtureCategory.HUMAN_FACING_DEVICE_NAMES,
        ),
        text,
    )
    provider = PiperTTSProvider(
        PiperTTSConfig(
            executable_path=Path(executable),
            voice_model_path=Path(voice),
            output_dir=Path(output_dir),
        )
    )
    return ProviderBakeOffReport(
        provider=provider.identity,
        fixture_set="voice-phase-2b-local-files",
        tts_results=(provider.evaluate_tts(fixture),),
        privacy_notes=("approved phrase fixtures only", "no speaker playback"),
        cost_quota_notes=("local Piper execution; voice licensing must be reviewed",),
        known_limitations=("file-output only", "human naturalness not evaluated"),
        recommendation=ProviderRecommendation.CONTINUE,
        synthetic_only=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
