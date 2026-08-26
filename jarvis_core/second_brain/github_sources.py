"""GitHub source adapter for Second Brain source indexing.

This module is the only Second Brain source-index module that performs GitHub
HTTP access. The index and retriever remain network-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import KnowledgeConfidence, KnowledgeFreshness, KnowledgeSensitivity
from .sources import SourceAdapter, SourceAuthority, SourceRecord, SourceType


MAX_GITHUB_SOURCE_BYTES = 96 * 1024
DEFAULT_GITHUB_SOURCE_PATHS = (
    "docs/project/PROJECT_STATE.md",
    "docs/design/SECOND_BRAIN_MEMORY_BOUNDARY.md",
    "docs/design/SECOND_BRAIN_STORAGE_PERSISTENCE_BOUNDARY.md",
    "docs/ai/README.md",
)


class GitHubSourceError(ValueError):
    """Bounded GitHub connector error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class GitHubFileSnapshot:
    repository: str
    path: str
    ref: str
    commit_sha: str
    blob_sha: str
    html_url: str
    content: str
    fetched_at: str = "live"


class GitHubSourceTransport(Protocol):
    def fetch_file(self, repository: str, path: str, ref: str) -> GitHubFileSnapshot:
        raise NotImplementedError


class GitHubApiTransport:
    """Small GitHub Contents API transport with optional bearer token."""

    def __init__(self, *, token: str | None = None, timeout_seconds: float = 10.0):
        self._token = token
        self._timeout_seconds = timeout_seconds

    def fetch_file(self, repository: str, path: str, ref: str) -> GitHubFileSnapshot:
        commit_sha = self._fetch_commit_sha(repository, ref)
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        payload = self._request_json(
            f"https://api.github.com/repos/{repository}/contents/{encoded_path}?ref={quote(commit_sha, safe='')}"
        )
        if payload.get("type") != "file":
            raise GitHubSourceError("github_source_not_file")
        encoded_content = payload.get("content")
        if not isinstance(encoded_content, str):
            raise GitHubSourceError("github_source_malformed")
        try:
            raw = base64.b64decode(encoded_content, validate=False)
        except ValueError as exc:
            raise GitHubSourceError("github_source_malformed") from exc
        if len(raw) > MAX_GITHUB_SOURCE_BYTES:
            raise GitHubSourceError("github_source_too_large")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitHubSourceError("github_source_malformed") from exc
        blob_sha = payload.get("sha")
        html_url = payload.get("html_url")
        if not isinstance(blob_sha, str) or not isinstance(html_url, str):
            raise GitHubSourceError("github_source_malformed")
        return GitHubFileSnapshot(
            repository=repository,
            path=path,
            ref=ref,
            commit_sha=commit_sha,
            blob_sha=blob_sha,
            html_url=html_url,
            content=content,
        )

    def _fetch_commit_sha(self, repository: str, ref: str) -> str:
        payload = self._request_json(
            f"https://api.github.com/repos/{repository}/commits/{quote(ref, safe='')}"
        )
        sha = payload.get("sha")
        if not isinstance(sha, str) or not sha:
            raise GitHubSourceError("github_source_malformed")
        return sha

    def _request_json(self, url: str) -> dict[str, object]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "JarvisOS-SecondBrainSourceAdapter",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                data = response.read(MAX_GITHUB_SOURCE_BYTES * 2)
        except HTTPError as exc:
            raise GitHubSourceError(_github_error_from_status(exc.code)) from exc
        except TimeoutError as exc:
            raise GitHubSourceError("github_source_timeout") from exc
        except URLError as exc:
            raise GitHubSourceError("github_source_unavailable") from exc
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubSourceError("github_source_malformed") from exc
        if not isinstance(payload, dict):
            raise GitHubSourceError("github_source_malformed")
        return payload


class GitHubSourceAdapter(SourceAdapter):
    """Enumerate an explicitly bounded set of GitHub repository documents."""

    def __init__(
        self,
        *,
        repository: str,
        ref: str,
        paths: tuple[str, ...] = DEFAULT_GITHUB_SOURCE_PATHS,
        transport: GitHubSourceTransport | None = None,
    ):
        self._repository = _validate_repository(repository)
        self._ref = _validate_ref(ref)
        self._paths = tuple(_validate_path(path) for path in paths)
        if not self._paths:
            raise GitHubSourceError("github_source_path_required")
        self._transport = transport or GitHubApiTransport()

    @property
    def source_scope(self) -> str:
        return f"{SourceType.GITHUB.value}:{self._repository}:{self._ref}"

    def enumerate_records(self) -> tuple[SourceRecord, ...]:
        records = []
        for path in self._paths:
            snapshot = self._transport.fetch_file(self._repository, path, self._ref)
            records.append(_record_from_snapshot(snapshot))
        return tuple(records)


def _record_from_snapshot(snapshot: GitHubFileSnapshot) -> SourceRecord:
    if snapshot.repository == "" or snapshot.path == "" or snapshot.commit_sha == "":
        raise GitHubSourceError("github_source_malformed")
    if len(snapshot.content.encode("utf-8")) > MAX_GITHUB_SOURCE_BYTES:
        raise GitHubSourceError("github_source_too_large")
    authority = _authority_for_path(snapshot.path, snapshot.content)
    title = _title_for_path(snapshot.path, snapshot.content)
    content = _bounded_content(snapshot.content)
    source_reference = (
        f"https://github.com/{snapshot.repository}/blob/{snapshot.commit_sha}/{snapshot.path}"
    )
    return SourceRecord(
        source_id=_source_id(snapshot.repository, snapshot.path),
        source_type=SourceType.GITHUB,
        source_reference=source_reference,
        title=title,
        topic=_topic_for_path(snapshot.path, title),
        content=content,
        captured_at=snapshot.fetched_at or snapshot.commit_sha,
        freshness=KnowledgeFreshness.CURRENT,
        authority=authority,
        confidence=KnowledgeConfidence.HIGH,
        sensitivity=KnowledgeSensitivity.ORDINARY,
        user_scope="system",
        safe_explanation=(
            "Live GitHub source snapshot; current source should outrank stale indexed snapshots."
        ),
    )


def _validate_repository(repository: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise GitHubSourceError("github_repository_invalid")
    return repository


def _validate_ref(ref: str) -> str:
    if not ref or ref.startswith("-") or ".." in ref or any(char in ref for char in "\\ ~^:?*["):
        raise GitHubSourceError("github_ref_invalid")
    return ref


def _validate_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized:
        raise GitHubSourceError("github_path_invalid")
    if normalized.startswith(".git/") or normalized.endswith("/"):
        raise GitHubSourceError("github_path_invalid")
    if not normalized.endswith(".md"):
        raise GitHubSourceError("github_path_unsupported")
    return normalized


def _source_id(repository: str, path: str) -> str:
    value = f"{repository}/{path}".lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _authority_for_path(path: str, content: str) -> SourceAuthority:
    if path == "docs/project/PROJECT_STATE.md":
        return SourceAuthority.PROJECT_STATE
    if path.startswith("docs/design/") and "Status: Accepted" in content:
        return SourceAuthority.DESIGN_ADR
    if path.endswith("README.md") or "/README.md" in path:
        return SourceAuthority.NOTE
    return SourceAuthority.NOTE


def _title_for_path(path: str, content: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()[:120]
    return path.rsplit("/", 1)[-1]


def _topic_for_path(path: str, title: str) -> str:
    terms = re.sub(r"[^A-Za-z0-9]+", " ", f"{path} {title}").lower()
    return " ".join(term for term in terms.split() if term)


def _bounded_content(content: str) -> str:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return "\n".join(lines)[:4000]


def _github_error_from_status(status_code: int) -> str:
    if status_code in (401, 403):
        return "github_source_unauthorized"
    if status_code == 404:
        return "github_source_missing"
    if status_code == 429:
        return "github_source_rate_limited"
    if 500 <= status_code < 600:
        return "github_source_unavailable"
    return "github_source_protocol_error"
