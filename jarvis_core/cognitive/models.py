"""Small value objects for the deterministic cognitive vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConfidenceBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXPLICIT = "explicit"


class Freshness(str, Enum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    EXPIRED = "expired"


class EvidenceOrigin(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"
    MEMORY = "memory"
    LEARNING = "learning"
    DEVICE_STATE = "device_state"
    SYSTEM = "system"


class Sensitivity(str, Enum):
    ORDINARY = "ordinary"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    IMPORTANT = "important"
    URGENT = "urgent"


class Relevance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class JudgmentAction(str, Enum):
    SUGGEST = "suggest"
    DEFER = "defer"
    CLARIFY = "clarify"
    ABSTAIN = "abstain"
    PROPOSE_MEMORY = "propose_memory"


class AttentionAction(str, Enum):
    SURFACE = "surface"
    DEFER = "defer"
    SILENCE = "silence"
    PRIVATE_SURFACE = "private_surface"


@dataclass(frozen=True)
class Signal:
    kind: str
    confidence: ConfidenceBand
    freshness: Freshness
    provenance: str
    origin: EvidenceOrigin
    sensitivity: Sensitivity = Sensitivity.ORDINARY
    user_scope: str = "system"
    urgency: Urgency = Urgency.NORMAL
    relevance: Relevance = Relevance.MEDIUM
    safe_explanation: str = ""
    observation_count: int = 1
    expires_at: str | None = None


@dataclass(frozen=True)
class MemoryPreference:
    key: str
    value: str
    approved: bool
    safe_explanation: str


@dataclass(frozen=True)
class ContextSnapshot:
    active_modes: tuple[str, ...]
    hypotheses: tuple[Signal, ...]
    explicit_corrections: tuple[Signal, ...]

    def has_mode(self, mode: str) -> bool:
        return mode in self.active_modes


@dataclass(frozen=True)
class PatternEvidence:
    pattern_id: str
    observation_count: int
    confidence: ConfidenceBand
    safe_explanation: str


@dataclass(frozen=True)
class JudgmentResult:
    action: JudgmentAction
    recommendation: str
    confidence: ConfidenceBand
    safe_explanation: str
    authorized_execution: bool = False
    memory_write_requested: bool = False
    rule_created: bool = False
    delegation_created: bool = False
    confirmation_bypassed: bool = False


@dataclass(frozen=True)
class AttentionResult:
    action: AttentionAction
    surface: str
    delivered: bool
    safe_explanation: str


@dataclass(frozen=True)
class ScenarioInput:
    scenario_id: str
    name: str
    signals: tuple[Signal, ...]
    memory_preferences: tuple[MemoryPreference, ...] = ()
    available_surfaces: tuple[str, ...] = ("dashboard",)
    expected_judgment: JudgmentAction = JudgmentAction.ABSTAIN
    expected_attention: AttentionAction = AttentionAction.SILENCE
