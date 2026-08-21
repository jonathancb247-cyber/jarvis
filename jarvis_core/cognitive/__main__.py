"""Command-line diagnostic surface for the deterministic cognitive benchmark."""

from __future__ import annotations

import argparse

from .benchmark import CognitiveBenchmarkRunner, build_phase1_scenarios
from .reporting import CognitiveReportRenderer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the local JarvisOS cognitive benchmark report.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = CognitiveBenchmarkRunner(build_phase1_scenarios()).run()
    renderer = CognitiveReportRenderer()
    if args.format == "json":
        print(renderer.render_json(report), end="")
    else:
        print(renderer.render_text(report), end="")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
