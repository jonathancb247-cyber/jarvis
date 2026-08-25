"""Command-line diagnostic surface for deterministic Second Brain retrieval."""

from __future__ import annotations

import argparse
import sys

from .fixtures import build_seed_knowledge
from .reporting import SecondBrainReportRenderer
from .repository import SQLiteKnowledgeRepository, SecondBrainStorageError, seed_repository
from .retrieval import InMemoryKnowledgeRetriever, build_demo_queries, run_demo_queries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render deterministic Second Brain retrieval diagnostics.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--query", action="append", help="Run one or more explicit deterministic lookup queries.")
    parser.add_argument("--storage", choices=("in-memory", "sqlite"), default="in-memory")
    parser.add_argument("--db", help="Explicit local SQLite path for fixture-only diagnostics.")
    parser.add_argument("--seed-fixtures", action="store_true", help="Insert the synthetic fixture dataset into SQLite.")
    parser.add_argument("--user-scope", help="Limit SQLite diagnostic retrieval to one user_scope.")
    args = parser.parse_args(argv)

    try:
        retriever = _build_retriever(args)
    except SecondBrainStorageError as exc:
        print(f"Second Brain storage error: {exc.code}", file=sys.stderr)
        return 1

    queries = tuple(args.query) if args.query else build_demo_queries()
    results = tuple(retriever.retrieve(query) for query in queries) if args.query else run_demo_queries(retriever)
    renderer = SecondBrainReportRenderer()
    if args.format == "json":
        print(renderer.render_json(results), end="")
    else:
        print(renderer.render_text(results), end="")
    return 0


def _build_retriever(args: argparse.Namespace) -> InMemoryKnowledgeRetriever:
    if args.storage == "in-memory":
        if args.db:
            raise SecondBrainStorageError("sqlite_db_requires_sqlite_storage")
        return InMemoryKnowledgeRetriever()

    if not args.db:
        raise SecondBrainStorageError("sqlite_db_required")

    repository = SQLiteKnowledgeRepository(args.db)
    repository.initialize()
    if args.seed_fixtures:
        seed_repository(repository, build_seed_knowledge())
    return InMemoryKnowledgeRetriever(repository.list(user_scope=args.user_scope))


if __name__ == "__main__":
    raise SystemExit(main())
