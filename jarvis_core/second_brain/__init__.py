"""Deterministic in-memory Second Brain retrieval helpers for JarvisOS."""

from .fixtures import build_seed_knowledge
from .github_sources import (
    DEFAULT_GITHUB_SOURCE_PATHS,
    GitHubApiTransport,
    GitHubFileSnapshot,
    GitHubSourceAdapter,
    GitHubSourceError,
)
from .index import SOURCE_INDEX_SCHEMA_VERSION, SQLiteSourceIndex, SourceIndexError
from .models import (
    KnowledgeConfidence,
    KnowledgeFreshness,
    KnowledgeItem,
    KnowledgeKind,
    KnowledgeOrigin,
    KnowledgeSensitivity,
    RetrievalResult,
    RetrievalStatus,
)
from .reporting import SecondBrainReportRenderer
from .repository import (
    InMemoryKnowledgeRepository,
    KnowledgeRepository,
    SECOND_BRAIN_SCHEMA_VERSION,
    SQLiteKnowledgeRepository,
    SecondBrainStorageError,
    seed_repository,
)
from .retrieval import InMemoryKnowledgeRetriever, build_demo_queries, run_demo_queries
from .source_retrieval import (
    DeterministicSemanticScorer,
    SourceHybridRetriever,
    SourceReportRenderer,
    build_source_demo_queries,
    run_source_demo_queries,
)
from .sources import (
    IndexedSourceDocument,
    LocalMarkdownSourceAdapter,
    SourceAdapter,
    SourceAuthority,
    SourceRecord,
    SourceRetrievalResult,
    SourceRetrievalStatus,
    SourceType,
    build_source_fixture_records,
    parse_markdown_source,
    write_source_fixture_markdown,
)

__all__ = [
    "InMemoryKnowledgeRetriever",
    "InMemoryKnowledgeRepository",
    "IndexedSourceDocument",
    "KnowledgeConfidence",
    "KnowledgeFreshness",
    "KnowledgeItem",
    "KnowledgeKind",
    "KnowledgeOrigin",
    "KnowledgeRepository",
    "KnowledgeSensitivity",
    "LocalMarkdownSourceAdapter",
    "RetrievalResult",
    "RetrievalStatus",
    "SECOND_BRAIN_SCHEMA_VERSION",
    "SOURCE_INDEX_SCHEMA_VERSION",
    "SQLiteKnowledgeRepository",
    "SQLiteSourceIndex",
    "SecondBrainReportRenderer",
    "SecondBrainStorageError",
    "SourceAdapter",
    "SourceAuthority",
    "SourceHybridRetriever",
    "SourceIndexError",
    "SourceRecord",
    "SourceReportRenderer",
    "SourceRetrievalResult",
    "SourceRetrievalStatus",
    "SourceType",
    "DeterministicSemanticScorer",
    "DEFAULT_GITHUB_SOURCE_PATHS",
    "GitHubApiTransport",
    "GitHubFileSnapshot",
    "GitHubSourceAdapter",
    "GitHubSourceError",
    "build_demo_queries",
    "build_seed_knowledge",
    "build_source_demo_queries",
    "build_source_fixture_records",
    "parse_markdown_source",
    "run_demo_queries",
    "run_source_demo_queries",
    "seed_repository",
    "write_source_fixture_markdown",
]
