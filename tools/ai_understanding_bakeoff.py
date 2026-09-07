"""Opt-in local AI understanding role bake-off helper.

This is evaluation tooling only. It resolves model extraction hints into
validated plans for reporting and never executes Runtime, Drivers or commands.
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

from jarvis_core.ai.gemma_android_bridge import (  # noqa: E402
    DEFAULT_ANDROID_BRIDGE_PORT,
    GemmaAndroidBridgeConfig,
    GemmaAndroidBridgeTransport,
)
from jarvis_core.ai.gemma_understanding import (  # noqa: E402
    GemmaLocalUnderstandingProvider,
    GemmaUnderstandingProviderConfig,
)
from jarvis_core.ai.understanding_bakeoff import (  # noqa: E402
    UnderstandingRoleBakeOff,
    build_default_understanding_fixtures,
    summarize_understanding_results,
)


def main(argv=None) -> int:
    args = _parse_args(argv)
    payload = run_gemma_understanding_bakeoff(
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


def run_gemma_understanding_bakeoff(
    model: str,
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_ANDROID_BRIDGE_PORT,
    timeout_seconds: int = 60,
    maximum_output_tokens: int = 256,
    transport=None,
    progress_stream=None,
    clock=perf_counter,
) -> dict[str, object]:
    provider_name = f"gemma-local-understanding:{model}"
    provider = GemmaLocalUnderstandingProvider(
        GemmaUnderstandingProviderConfig(
            model=model,
            timeout_seconds=timeout_seconds,
            maximum_output_tokens=maximum_output_tokens,
        ),
        transport=transport
        or GemmaAndroidBridgeTransport(GemmaAndroidBridgeConfig(host=host, port=port)),
    )
    fixtures = build_default_understanding_fixtures()
    bakeoff = UnderstandingRoleBakeOff(
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
            status = result.normalized_failure or result.final_plan_kind or "unknown"
            latency = (
                f"{result.latency_ms}ms"
                if result.latency_ms is not None
                else "latency_unavailable"
            )
            print(
                f"[{index}/{len(fixtures)}] finished {fixture.fixture_id}: "
                f"{status}, {latency}",
                file=progress_stream,
                flush=True,
            )
    results = tuple(results)
    return {
        "provider": "gemma-local-understanding",
        "model": model,
        "fixture_set": "ai-understanding-role-bakeoff",
        "execution": {
            "runtime": False,
            "drivers": False,
            "stt": False,
            "ai_action_plan_execution": False,
            "cloud_fallback": False,
        },
        "results": [result.as_dict() for result in results],
        "summary": summarize_understanding_results(
            results,
            provider_name=provider_name,
        ).as_dict(),
    }


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Local AI understanding bake-off helper")
    subparsers = parser.add_subparsers(dest="provider", required=True)

    gemma = subparsers.add_parser(
        "gemma-local",
        help="Evaluate one local Gemma model through the Android bridge",
    )
    gemma.add_argument("--model", required=True)
    gemma.add_argument("--host", default="127.0.0.1")
    gemma.add_argument("--port", type=int, default=DEFAULT_ANDROID_BRIDGE_PORT)
    gemma.add_argument("--timeout-seconds", type=int, default=60)
    gemma.add_argument("--max-output-tokens", type=int, default=256)

    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())

