"""Experimental simulated discovery boundary for JarvisOS."""

from dataclasses import dataclass, field


class DiscoveryProviderUnavailable(Exception):
    """Raised when an experimental discovery provider is unavailable."""


class DiscoveryScanError(Exception):
    """Raised when an experimental discovery scan fails."""


@dataclass(frozen=True)
class DiscoveryCandidate:
    """Temporary sanitized candidate produced by discovery."""

    candidate_id: str
    display_name: str
    transport: str
    manufacturer: str = None
    model: str = None
    capability_hints: tuple = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.candidate_id, str) or not self.candidate_id:
            raise ValueError("DiscoveryCandidate candidate_id must be a non-empty string")
        if not isinstance(self.display_name, str) or not self.display_name:
            raise ValueError("DiscoveryCandidate display_name must be a non-empty string")
        if not isinstance(self.transport, str) or not self.transport:
            raise ValueError("DiscoveryCandidate transport must be a non-empty string")
        if self.manufacturer is not None and (
            not isinstance(self.manufacturer, str) or not self.manufacturer
        ):
            raise ValueError(
                "DiscoveryCandidate manufacturer must be None or a non-empty string"
            )
        if self.model is not None and (
            not isinstance(self.model, str) or not self.model
        ):
            raise ValueError("DiscoveryCandidate model must be None or a non-empty string")
        if not isinstance(self.capability_hints, (list, tuple)):
            raise ValueError("DiscoveryCandidate capability_hints must be a list")
        for hint in self.capability_hints:
            if not isinstance(hint, str) or not hint:
                raise ValueError(
                    "DiscoveryCandidate capability_hints must contain non-empty strings"
                )
        object.__setattr__(self, "capability_hints", tuple(self.capability_hints))


class SimulatedDiscoveryProvider:
    """Experimental deterministic provider for simulated device discovery."""

    def __init__(self, candidates=None, available=True, fail_scan=False):
        if not isinstance(available, bool):
            raise ValueError("SimulatedDiscoveryProvider available must be a bool")
        if not isinstance(fail_scan, bool):
            raise ValueError("SimulatedDiscoveryProvider fail_scan must be a bool")
        self._available = available
        self._fail_scan = fail_scan
        self._candidates = self._default_candidates() if candidates is None else candidates

    def scan(self):
        """Return deterministic simulated discovery candidates."""
        if not self._available:
            raise DiscoveryProviderUnavailable("simulated discovery provider unavailable")
        if self._fail_scan:
            raise DiscoveryScanError("simulated discovery scan failed")
        return list(self._candidates)

    def _default_candidates(self):
        return [
            DiscoveryCandidate(
                candidate_id="simulated-light-1",
                display_name="Simulated Light",
                transport="simulated",
                manufacturer="JarvisOS",
                model="SimulatedLight",
                capability_hints=("light", "power"),
            )
        ]


class DiscoveryCandidateStore:
    """Experimental in-memory store for the latest explicit discovery result."""

    def __init__(self):
        self._candidates = {}

    def replace(self, candidates):
        if not isinstance(candidates, (list, tuple)):
            raise ValueError("DiscoveryCandidateStore.replace expects a list")
        next_candidates = {}
        for candidate in candidates:
            if not isinstance(candidate, DiscoveryCandidate):
                raise TypeError(
                    "DiscoveryCandidateStore stores only DiscoveryCandidate objects"
                )
            next_candidates[candidate.candidate_id] = candidate
        self._candidates = next_candidates

    def get(self, candidate_id):
        self._validate_candidate_id(candidate_id)
        if candidate_id not in self._candidates:
            raise KeyError(f"Discovery candidate not found: {candidate_id}")
        return self._candidates[candidate_id]

    def list(self):
        return list(self._candidates.values())

    def clear(self):
        self._candidates = {}

    def _validate_candidate_id(self, candidate_id):
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError("DiscoveryCandidateStore candidate_id must be a non-empty string")
