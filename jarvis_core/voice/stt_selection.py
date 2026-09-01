"""Provider-neutral STT selection for local voice evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from .provider_contracts import (
    ProviderDeployment,
    ProviderFailure,
    ProviderFailureCategory,
    STTEvaluationProvider,
    STTEvaluationResult,
    STTFixture,
    normalize_provider_exception,
)


@dataclass(frozen=True)
class STTProviderCandidate:
    provider: STTEvaluationProvider
    name: str | None = None
    enabled: bool = True
    priority: int = 100

    def __post_init__(self) -> None:
        if self.name is not None and not self.name.strip():
            raise ValueError("candidate name must not be blank")

    @property
    def candidate_name(self) -> str:
        return self.name or self.provider.identity.name

    @property
    def deployment(self) -> ProviderDeployment:
        return self.provider.identity.deployment


@dataclass(frozen=True)
class STTSelectionPolicy:
    prefer_local: bool = True
    allow_cloud_fallback: bool = False
    fallback_on_unavailable: bool = True
    fallback_on_failure: bool = False


@dataclass(frozen=True)
class STTSelectionDecision:
    selected_provider: str | None
    selected_deployment: ProviderDeployment | None
    reason: str
    fallback_used: bool = False
    primary_provider: str | None = None
    primary_failure: ProviderFailure | None = None
    selected_failure: ProviderFailure | None = None
    attempted_providers: tuple[str, ...] = ()


@dataclass(frozen=True)
class STTSelectionResult:
    decision: STTSelectionDecision
    result: STTEvaluationResult | None = None


class STTProviderSelector:
    def __init__(
        self,
        candidates: tuple[STTProviderCandidate, ...],
        policy: STTSelectionPolicy | None = None,
    ) -> None:
        self._candidates = tuple(candidates)
        self._policy = policy or STTSelectionPolicy()

    def evaluate_stt(self, fixture: STTFixture) -> STTSelectionResult:
        ordered = self._ordered_candidates()
        if not ordered:
            return STTSelectionResult(
                STTSelectionDecision(
                    selected_provider=None,
                    selected_deployment=None,
                    reason="no_provider_available",
                )
            )

        primary = ordered[0]
        attempted = (primary.candidate_name,)
        try:
            primary_result = primary.provider.evaluate_stt(fixture)
        except Exception as error:
            failure = normalize_provider_exception(error)
            if self._fallback_allowed_for(failure):
                fallback = self._first_cloud_fallback(ordered[1:])
                if fallback is not None:
                    return self._evaluate_fallback_after_failure(
                        fixture,
                        primary,
                        failure,
                        fallback,
                    )
            return STTSelectionResult(
                STTSelectionDecision(
                    selected_provider=primary.candidate_name,
                    selected_deployment=primary.deployment,
                    reason="primary_provider_exception",
                    primary_provider=primary.candidate_name,
                    primary_failure=failure,
                    selected_failure=failure,
                    attempted_providers=attempted,
                )
            )
        if primary_result.failure is None:
            return STTSelectionResult(
                STTSelectionDecision(
                    selected_provider=primary.candidate_name,
                    selected_deployment=primary.deployment,
                    reason=self._primary_success_reason(primary),
                    primary_provider=primary.candidate_name,
                    attempted_providers=attempted,
                ),
                primary_result,
            )

        if not self._fallback_allowed_for(primary_result.failure):
            return STTSelectionResult(
                STTSelectionDecision(
                    selected_provider=primary.candidate_name,
                    selected_deployment=primary.deployment,
                    reason=self._fallback_blocked_reason(primary_result.failure),
                    primary_provider=primary.candidate_name,
                    primary_failure=primary_result.failure,
                    selected_failure=primary_result.failure,
                    attempted_providers=attempted,
                ),
                primary_result,
            )

        fallback = self._first_cloud_fallback(ordered[1:])
        if fallback is None:
            return STTSelectionResult(
                STTSelectionDecision(
                    selected_provider=primary.candidate_name,
                    selected_deployment=primary.deployment,
                    reason="primary_failed_no_fallback_available",
                    primary_provider=primary.candidate_name,
                    primary_failure=primary_result.failure,
                    selected_failure=primary_result.failure,
                    attempted_providers=attempted,
                ),
                primary_result,
            )

        return self._evaluate_fallback_after_failure(
            fixture,
            primary,
            primary_result.failure,
            fallback,
        )

    def _evaluate_fallback_after_failure(
        self,
        fixture: STTFixture,
        primary: STTProviderCandidate,
        primary_failure: ProviderFailure,
        fallback: STTProviderCandidate,
    ) -> STTSelectionResult:
        attempted = (primary.candidate_name, fallback.candidate_name)
        try:
            fallback_result = fallback.provider.evaluate_stt(fixture)
        except Exception as error:
            return STTSelectionResult(
                STTSelectionDecision(
                    selected_provider=fallback.candidate_name,
                    selected_deployment=fallback.deployment,
                    reason="fallback_provider_exception",
                    fallback_used=True,
                    primary_provider=primary.candidate_name,
                    primary_failure=primary_failure,
                    selected_failure=normalize_provider_exception(error),
                    attempted_providers=attempted,
                )
            )
        return STTSelectionResult(
            STTSelectionDecision(
                selected_provider=fallback.candidate_name,
                selected_deployment=fallback.deployment,
                reason=self._fallback_reason(primary_failure),
                fallback_used=True,
                primary_provider=primary.candidate_name,
                primary_failure=primary_failure,
                attempted_providers=attempted,
            ),
            fallback_result,
        )

    def _ordered_candidates(self) -> tuple[STTProviderCandidate, ...]:
        enabled = [
            candidate
            for candidate in self._candidates
            if candidate.enabled
            and (
                candidate.deployment == ProviderDeployment.LOCAL
                or self._policy.allow_cloud_fallback
            )
        ]
        return tuple(sorted(enabled, key=self._sort_key))

    def _sort_key(self, candidate: STTProviderCandidate) -> tuple[int, int, str]:
        local_rank = 0
        if self._policy.prefer_local:
            local_rank = 0 if candidate.deployment == ProviderDeployment.LOCAL else 1
        return (local_rank, candidate.priority, candidate.candidate_name)

    def _fallback_allowed_for(self, failure: ProviderFailure) -> bool:
        if not self._policy.allow_cloud_fallback:
            return False
        if failure.category == ProviderFailureCategory.UNAVAILABLE:
            return self._policy.fallback_on_unavailable
        return self._policy.fallback_on_failure

    def _fallback_blocked_reason(self, failure: ProviderFailure) -> str:
        if not self._policy.allow_cloud_fallback:
            return "cloud_fallback_disabled"
        if failure.category == ProviderFailureCategory.UNAVAILABLE:
            return "unavailable_fallback_disabled"
        return "failure_fallback_disabled"

    def _first_cloud_fallback(
        self,
        candidates: tuple[STTProviderCandidate, ...],
    ) -> STTProviderCandidate | None:
        for candidate in candidates:
            if candidate.deployment == ProviderDeployment.CLOUD:
                return candidate
        return None

    def _primary_success_reason(self, candidate: STTProviderCandidate) -> str:
        if candidate.deployment == ProviderDeployment.LOCAL and self._policy.prefer_local:
            return "local_preferred"
        return "primary_selected"

    def _fallback_reason(self, failure: ProviderFailure) -> str:
        if failure.category == ProviderFailureCategory.UNAVAILABLE:
            return "primary_unavailable_cloud_fallback_selected"
        return "primary_failed_cloud_fallback_selected"
