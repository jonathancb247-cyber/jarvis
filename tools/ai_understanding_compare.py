"""Opt-in local AI understanding model-comparison helper.

Compares local understanding/extraction candidates over the exact same fixed
fixture set and DeterministicUnderstandingResolver used by the understanding
role bake-off. Evaluation tooling only: it never executes Runtime, Drivers,
tools, STT, Voice, or a cloud fallback.

Each --model runs a full 9-fixture pass through the Android bridge bound to
127.0.0.1. The bridge serves whatever on-device artifact is loaded for that
process; the operator must load the intended artifact before each pass. There
is no model router or selector: the --model value is a lab label recorded in
the report, never a runtime selection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jarvis_core.ai.gemma_android_bridge import (  # noqa: E402
    DEFAULT_ANDROID_BRIDGE_PORT,
    GemmaAndroidBridgeConfig,
    GemmaAndroidBridgeTransport,
)
from jarvis_core.ai.gemma_local import GemmaLocalTransport  # noqa: E402
from jarvis_core.ai.gemma_understanding import (  # noqa: E402
    GemmaLocalUnderstandingProvider,
    GemmaUnderstandingProviderConfig,
)
from jarvis_core.ai.understanding_model_comparison import (  # noqa: E402
    ServerResponseRecord,
    run_understanding_model_comparison,
)


class ObservingGemmaAndroidBridgeTransport(GemmaAndroidBridgeTransport):
    """Android bridge transport that records every response for the lab hook."""

    def __init__(self, config: GemmaAndroidBridgeConfig) -> None:
        super().__init__(config, on_response=self._record_response)
        self.records: list[tuple[int, bytes]] = []

    def _record_response(self, status: int, raw: bytes) -> None:
        self.records.append((status, raw))


def run_android_understanding_model_comparison(
    models: Sequence[str],
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_ANDROID_BRIDGE_PORT,
    timeout_seconds: int = 60,
    maximum_output_tokens: int = 256,
    baseline_model: str | None = None,
    transport_factory: Callable[[str], GemmaLocalTransport] | None = None,
    progress_stream=None,
    clock=perf_counter,
    memory_rss_mb: dict[str, float] | None = None,
) -> dict[str, object]:
    models = tuple(models)
    if not models:
        raise ValueError("at least one --model is required")
    baseline = baseline_model or models[0]

    def default_transport(model: str) -> GemmaLocalTransport:
        return ObservingGemmaAndroidBridgeTransport(
            GemmaAndroidBridgeConfig(host=host, port=port)
        )

    factory = transport_factory or default_transport
    providers = {}
    transports = {}
    for model in models:
        transport = factory(model)
        transports[model] = transport
        providers[model] = GemmaLocalUnderstandingProvider(
            GemmaUnderstandingProviderConfig(
                model=model,
                timeout_seconds=timeout_seconds,
                maximum_output_tokens=maximum_output_tokens,
            ),
            transport=transport,
        )

    def observed(model: str) -> tuple[ServerResponseRecord, ...]:
        transport = transports[model]
        raw_records = getattr(transport, "records", None) or []
        return tuple(
            ServerResponseRecord.from_raw(status, raw) for status, raw in raw_records
        )

    def on_fixture(model: str, index: int, total: int, result) -> None:
        if progress_stream is not None:
            status = result.normalized_failure or result.final_plan_kind or "unknown"
            print(
                f"[{model}] [{index}/{total}] {result.fixture_id}: {status}",
                file=progress_stream,
                flush=True,
            )

    return run_understanding_model_comparison(
        providers,
        baseline_model=baseline,
        clock=clock,
        on_fixture=on_fixture,
        server_records={model: lambda m=model: observed(m) for model in models},
        memory_rss_mb=memory_rss_mb,
    ).as_dict()


def main(argv=None) -> int:
    args = _parse_args(argv)
    payload = run_android_understanding_model_comparison(
        args.models,
        host=args.host,
        port=args.port,
        timeout_seconds=args.timeout_seconds,
        maximum_output_tokens=args.max_output_tokens,
        baseline_model=args.baseline_model,
        progress_stream=sys.stderr,
        clock=perf_counter,
        memory_rss_mb=args.memory_rss_mb,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Local AI understanding model-comparison helper",
        epilog=(
            "Run one pass per --model against a local Android bridge "
            "(127.0.0.1:8767). Load the intended on-device artifact before "
            "each pass; --model is a lab label only."
        ),
    )
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        required=True,
        metavar="LABEL",
        help="Lab label for one candidate pass (repeatable; first is baseline unless --baseline-model)",
    )
    parser.add_argument("--baseline-model", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_ANDROID_BRIDGE_PORT)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument(
        "--memory-rss-mb",
        dest="memory_rss_mb",
        action="append",
        default=None,
        metavar="MODEL=MB",
        help="Optional externally observed RSS (adb dumpsys meminfo) per label",
    )
    return _parse_memory(parser.parse_args(argv))


def _parse_memory(args) -> None:
    memory: dict[str, float] = {}
    for token in args.memory_rss_mb or ():
        model, separator, raw_value = token.partition("=")
        if not separator or not model.strip() or not raw_value.strip():
            raise SystemExit(f"invalid --memory-rss-mb token: {token!r} (expected MODEL=MB)")
        try:
            value = float(raw_value)
        except ValueError as error:
            raise SystemExit(f"invalid --memory-rss-mb value in: {token!r}") from error
        if value < 0:
            raise SystemExit(f"invalid --memory-rss-mb value in: {token!r}")
        memory[model.strip()] = value
    args.memory_rss_mb = memory
    return args


if __name__ == "__main__":
    raise SystemExit(main())