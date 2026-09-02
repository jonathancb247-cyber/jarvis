"""Opt-in structured AI provider bake-off helper.

This is evaluation tooling only. It does not build Runtime, call Planner, use
Drivers, execute AIActionPlan steps or perform provider fallback.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jarvis_core.ai.ollama import OllamaAIProvider, OllamaProviderConfig
from jarvis_core.ai.structured_bakeoff import (
    FIXED_TEMPORAL_CONTEXT,
    StructuredProviderBakeOff,
    build_default_structured_ai_fixtures,
    summarize_structured_ai_results,
)


def main(argv=None) -> int:
    args = _parse_args(argv)
    payload = run_ollama_bakeoff(
        args.model,
        host=args.host,
        port=args.port,
        timeout_seconds=args.timeout_seconds,
        maximum_output_tokens=args.max_output_tokens,
        progress_stream=sys.stderr,
        clock=perf_counter,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def run_ollama_bakeoff(
    model: str,
    *,
    host: str = "127.0.0.1",
    port: int = 11434,
    timeout_seconds: int = 60,
    maximum_output_tokens: int = 512,
    transport=None,
    progress_stream=None,
    clock=perf_counter,
) -> dict[str, object]:
    provider_name = f"ollama:{model}"
    provider = OllamaAIProvider(
        OllamaProviderConfig(
            model=model,
            host=host,
            port=port,
            timeout_seconds=timeout_seconds,
            maximum_output_tokens=maximum_output_tokens,
        ),
        transport=transport,
    )
    fixtures = build_default_structured_ai_fixtures()
    bakeoff = StructuredProviderBakeOff(
        provider,
        provider_name=provider_name,
        fixtures=fixtures,
        clock=clock,
    )
    results = []
    for index, fixture in enumerate(fixtures, start=1):
        if progress_stream is not None:
            print(
                f"[{index}/{len(fixtures)}] running {fixture.fixture_id}",
                file=progress_stream,
                flush=True,
            )
        result = bakeoff.evaluate_fixture(fixture)
        results.append(result)
        if progress_stream is not None:
            status = result.normalized_failure or "ok"
            latency = (
                f"{result.latency_ms}ms"
                if result.latency_ms is not None
                else "latency_unavailable"
            )
            print(
                f"[{index}/{len(fixtures)}] finished {fixture.fixture_id}: {status}, {latency}",
                file=progress_stream,
                flush=True,
            )
    results = tuple(results)
    return {
        "provider": "ollama",
        "model": model,
        "maximum_output_tokens": maximum_output_tokens,
        "fixture_set": "ai-structured-provider-bakeoff",
        "fixed_temporal_context": FIXED_TEMPORAL_CONTEXT,
        "execution": {
            "runtime": False,
            "drivers": False,
            "stt": False,
            "ai_action_plan_execution": False,
            "cloud_fallback": False,
        },
        "results": [result.as_dict() for result in results],
        "summary": summarize_structured_ai_results(
            results,
            provider_name=provider_name,
            fixtures=fixtures,
        ).as_dict(),
    }


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Structured AI provider bake-off helper")
    subparsers = parser.add_subparsers(dest="provider", required=True)

    ollama = subparsers.add_parser("ollama", help="Evaluate one local Ollama model")
    ollama.add_argument("--model", required=True)
    ollama.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost"])
    ollama.add_argument("--port", type=int, default=11434)
    ollama.add_argument("--timeout-seconds", type=int, default=60)
    ollama.add_argument("--max-output-tokens", type=int, default=512)

    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
