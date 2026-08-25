"""Command-line diagnostic surface for deterministic Second Brain retrieval."""

from __future__ import annotations

import argparse

from .reporting import SecondBrainReportRenderer
from .retrieval import InMemoryKnowledgeRetriever, build_demo_queries, run_demo_queries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render deterministic Second Brain retrieval diagnostics.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--query", action="append", help="Run one or more explicit deterministic lookup queries.")
    args = parser.parse_args(argv)

    retriever = InMemoryKnowledgeRetriever()
    queries = tuple(args.query) if args.query else build_demo_queries()
    results = tuple(retriever.retrieve(query) for query in queries) if args.query else run_demo_queries(retriever)
    renderer = SecondBrainReportRenderer()
    if args.format == "json":
        print(renderer.render_json(results), end="")
    else:
        print(renderer.render_text(results), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
