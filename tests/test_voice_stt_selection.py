import ast
from pathlib import Path
import unittest

from jarvis_core.voice.provider_contracts import (
    FixtureCategory,
    ProviderDeployment,
    ProviderFailure,
    ProviderFailureCategory,
    ProviderIdentity,
    STTCapabilities,
    STTEvaluationResult,
    STTFixture,
)
from jarvis_core.voice.stt_selection import (
    STTProviderCandidate,
    STTProviderSelector,
    STTSelectionPolicy,
)


class FakeSTTProvider:
    def __init__(
        self,
        name,
        deployment,
        *,
        failure=None,
        error=None,
        transcript=None,
    ):
        self.identity = ProviderIdentity(name, "stt", deployment, name)
        self.capabilities = STTCapabilities(local_offline=deployment == ProviderDeployment.LOCAL)
        self.failure = failure
        self.error = error
        self.transcript = transcript or f"{name} transcript"
        self.calls = []

    def evaluate_stt(self, fixture):
        self.calls.append(fixture)
        if self.error is not None:
            raise self.error
        if self.failure is not None:
            return STTEvaluationResult(
                self.identity,
                fixture.fixture_id,
                self.capabilities,
                failure=self.failure,
            )
        return STTEvaluationResult(
            self.identity,
            fixture.fixture_id,
            self.capabilities,
            final_transcript=self.transcript,
            transcript_latency_ms=1,
        )


class STTSelectionTests(unittest.TestCase):
    def test_local_success_is_preferred_and_cloud_is_not_called(self):
        local = FakeSTTProvider("local", ProviderDeployment.LOCAL)
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)
        selector = STTProviderSelector(
            (
                STTProviderCandidate(cloud),
                STTProviderCandidate(local),
            )
        )

        selected = selector.evaluate_stt(_fixture())

        self.assertEqual(selected.decision.selected_provider, "local")
        self.assertEqual(selected.decision.reason, "local_preferred")
        self.assertFalse(selected.decision.fallback_used)
        self.assertIsNone(selected.decision.primary_failure)
        self.assertEqual(selected.decision.attempted_providers, ("local",))
        self.assertEqual(len(local.calls), 1)
        self.assertEqual(len(cloud.calls), 0)
        self.assertEqual(selected.result.final_transcript, "local transcript")

    def test_local_unavailable_with_cloud_disabled_does_not_fallback(self):
        local_failure = ProviderFailure(ProviderFailureCategory.UNAVAILABLE, "unavailable")
        local = FakeSTTProvider("local", ProviderDeployment.LOCAL, failure=local_failure)
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)

        selected = STTProviderSelector(
            (
                STTProviderCandidate(local),
                STTProviderCandidate(cloud),
            )
        ).evaluate_stt(_fixture())

        self.assertEqual(selected.decision.selected_provider, "local")
        self.assertEqual(selected.decision.reason, "cloud_fallback_disabled")
        self.assertFalse(selected.decision.fallback_used)
        self.assertIs(selected.decision.primary_failure, local_failure)
        self.assertEqual(selected.decision.attempted_providers, ("local",))
        self.assertEqual(len(cloud.calls), 0)
        self.assertIs(selected.result.failure, local_failure)

    def test_cloud_candidate_is_never_executed_when_cloud_fallback_is_disabled(self):
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)

        selected = STTProviderSelector((STTProviderCandidate(cloud),)).evaluate_stt(_fixture())

        self.assertIsNone(selected.result)
        self.assertIsNone(selected.decision.selected_provider)
        self.assertEqual(selected.decision.reason, "no_provider_available")
        self.assertEqual(len(cloud.calls), 0)

    def test_local_unavailable_with_cloud_enabled_falls_back(self):
        local_failure = ProviderFailure(ProviderFailureCategory.UNAVAILABLE, "unavailable")
        local = FakeSTTProvider("local", ProviderDeployment.LOCAL, failure=local_failure)
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)
        selector = STTProviderSelector(
            (
                STTProviderCandidate(local),
                STTProviderCandidate(cloud),
            ),
            STTSelectionPolicy(allow_cloud_fallback=True),
        )

        selected = selector.evaluate_stt(_fixture())

        self.assertEqual(selected.decision.selected_provider, "cloud")
        self.assertEqual(
            selected.decision.reason,
            "primary_unavailable_cloud_fallback_selected",
        )
        self.assertTrue(selected.decision.fallback_used)
        self.assertIs(selected.decision.primary_failure, local_failure)
        self.assertEqual(selected.decision.attempted_providers, ("local", "cloud"))
        self.assertEqual(len(cloud.calls), 1)
        self.assertEqual(selected.result.final_transcript, "cloud transcript")

    def test_unavailable_fallback_can_be_disabled_independently(self):
        local_failure = ProviderFailure(ProviderFailureCategory.UNAVAILABLE, "unavailable")
        local = FakeSTTProvider("local", ProviderDeployment.LOCAL, failure=local_failure)
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)

        selected = STTProviderSelector(
            (
                STTProviderCandidate(local),
                STTProviderCandidate(cloud),
            ),
            STTSelectionPolicy(
                allow_cloud_fallback=True,
                fallback_on_unavailable=False,
                fallback_on_failure=True,
            ),
        ).evaluate_stt(_fixture())

        self.assertEqual(selected.decision.reason, "unavailable_fallback_disabled")
        self.assertFalse(selected.decision.fallback_used)
        self.assertIs(selected.decision.selected_failure, local_failure)
        self.assertEqual(len(cloud.calls), 0)

    def test_timeout_with_failure_fallback_disabled_does_not_fallback(self):
        local_failure = ProviderFailure(ProviderFailureCategory.TIMEOUT, "timeout")
        local = FakeSTTProvider("local", ProviderDeployment.LOCAL, failure=local_failure)
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)

        selected = STTProviderSelector(
            (
                STTProviderCandidate(local),
                STTProviderCandidate(cloud),
            ),
            STTSelectionPolicy(allow_cloud_fallback=True),
        ).evaluate_stt(_fixture())

        self.assertEqual(selected.decision.reason, "failure_fallback_disabled")
        self.assertFalse(selected.decision.fallback_used)
        self.assertIs(selected.decision.primary_failure, local_failure)
        self.assertIs(selected.decision.selected_failure, local_failure)
        self.assertEqual(len(cloud.calls), 0)

    def test_timeout_with_failure_fallback_enabled_uses_cloud(self):
        local_failure = ProviderFailure(ProviderFailureCategory.TIMEOUT, "timeout")
        local = FakeSTTProvider("local", ProviderDeployment.LOCAL, failure=local_failure)
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)

        selected = STTProviderSelector(
            (
                STTProviderCandidate(local),
                STTProviderCandidate(cloud),
            ),
            STTSelectionPolicy(
                allow_cloud_fallback=True,
                fallback_on_failure=True,
            ),
        ).evaluate_stt(_fixture())

        self.assertEqual(selected.decision.selected_provider, "cloud")
        self.assertEqual(
            selected.decision.reason,
            "primary_failed_cloud_fallback_selected",
        )
        self.assertTrue(selected.decision.fallback_used)
        self.assertIs(selected.decision.primary_failure, local_failure)
        self.assertEqual(selected.result.final_transcript, "cloud transcript")

    def test_unexpected_primary_exception_is_normalized_without_fake_result(self):
        local = FakeSTTProvider(
            "local",
            ProviderDeployment.LOCAL,
            error=RuntimeError("raw provider stack detail"),
        )
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)

        selected = STTProviderSelector(
            (
                STTProviderCandidate(local),
                STTProviderCandidate(cloud),
            )
        ).evaluate_stt(_fixture())

        self.assertIsNone(selected.result)
        self.assertEqual(selected.decision.reason, "primary_provider_exception")
        self.assertEqual(
            selected.decision.primary_failure.category,
            ProviderFailureCategory.PROVIDER_ERROR,
        )
        self.assertEqual(selected.decision.primary_failure.safe_message, "provider_error")
        self.assertEqual(selected.decision.selected_failure.safe_message, "provider_error")
        self.assertNotIn("raw provider stack detail", selected.decision.primary_failure.safe_message)
        self.assertEqual(len(cloud.calls), 0)

    def test_unexpected_primary_exception_can_fallback_when_failure_fallback_enabled(self):
        local = FakeSTTProvider(
            "local",
            ProviderDeployment.LOCAL,
            error=RuntimeError("raw provider stack detail"),
        )
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)

        selected = STTProviderSelector(
            (
                STTProviderCandidate(local),
                STTProviderCandidate(cloud),
            ),
            STTSelectionPolicy(allow_cloud_fallback=True, fallback_on_failure=True),
        ).evaluate_stt(_fixture())

        self.assertEqual(selected.decision.selected_provider, "cloud")
        self.assertEqual(
            selected.decision.reason,
            "primary_failed_cloud_fallback_selected",
        )
        self.assertTrue(selected.decision.fallback_used)
        self.assertEqual(
            selected.decision.primary_failure.category,
            ProviderFailureCategory.PROVIDER_ERROR,
        )
        self.assertEqual(len(cloud.calls), 1)
        self.assertEqual(selected.result.final_transcript, "cloud transcript")

    def test_fallback_exception_is_normalized_without_fake_result(self):
        local_failure = ProviderFailure(ProviderFailureCategory.TIMEOUT, "timeout")
        local = FakeSTTProvider("local", ProviderDeployment.LOCAL, failure=local_failure)
        cloud = FakeSTTProvider(
            "cloud",
            ProviderDeployment.CLOUD,
            error=RuntimeError("raw cloud failure"),
        )

        selected = STTProviderSelector(
            (
                STTProviderCandidate(local),
                STTProviderCandidate(cloud),
            ),
            STTSelectionPolicy(allow_cloud_fallback=True, fallback_on_failure=True),
        ).evaluate_stt(_fixture())

        self.assertIsNone(selected.result)
        self.assertEqual(selected.decision.reason, "fallback_provider_exception")
        self.assertTrue(selected.decision.fallback_used)
        self.assertIs(selected.decision.primary_failure, local_failure)
        self.assertEqual(selected.decision.selected_failure.safe_message, "provider_error")
        self.assertNotIn("raw cloud failure", selected.decision.selected_failure.safe_message)

    def test_no_provider_available_returns_no_result(self):
        selected = STTProviderSelector(
            (STTProviderCandidate(FakeSTTProvider("off", ProviderDeployment.LOCAL), enabled=False),)
        ).evaluate_stt(_fixture())

        self.assertIsNone(selected.result)
        self.assertIsNone(selected.decision.selected_provider)
        self.assertEqual(selected.decision.reason, "no_provider_available")
        self.assertEqual(selected.decision.attempted_providers, ())

    def test_disabled_candidates_are_never_executed(self):
        disabled_local = FakeSTTProvider("disabled", ProviderDeployment.LOCAL)
        enabled_local = FakeSTTProvider("enabled", ProviderDeployment.LOCAL)

        selected = STTProviderSelector(
            (
                STTProviderCandidate(disabled_local, enabled=False, priority=1),
                STTProviderCandidate(enabled_local, priority=10),
            )
        ).evaluate_stt(_fixture())

        self.assertEqual(selected.decision.selected_provider, "enabled")
        self.assertEqual(len(disabled_local.calls), 0)
        self.assertEqual(len(enabled_local.calls), 1)

    def test_order_is_deterministic(self):
        first = FakeSTTProvider("alpha", ProviderDeployment.LOCAL)
        second = FakeSTTProvider("beta", ProviderDeployment.LOCAL)
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)
        candidates = (
            STTProviderCandidate(cloud, priority=1),
            STTProviderCandidate(second, priority=5),
            STTProviderCandidate(first, priority=5),
        )

        selected = STTProviderSelector(candidates).evaluate_stt(_fixture())

        self.assertEqual(selected.decision.selected_provider, "alpha")
        self.assertEqual(len(first.calls), 1)
        self.assertEqual(len(second.calls), 0)
        self.assertEqual(len(cloud.calls), 0)

    def test_prefer_local_false_uses_priority_without_local_bias(self):
        local = FakeSTTProvider("local", ProviderDeployment.LOCAL)
        cloud = FakeSTTProvider("cloud", ProviderDeployment.CLOUD)

        selected = STTProviderSelector(
            (
                STTProviderCandidate(local, priority=10),
                STTProviderCandidate(cloud, priority=1),
            ),
            STTSelectionPolicy(prefer_local=False, allow_cloud_fallback=True),
        ).evaluate_stt(_fixture())

        self.assertEqual(selected.decision.selected_provider, "cloud")
        self.assertEqual(selected.decision.reason, "primary_selected")
        self.assertEqual(len(local.calls), 0)
        self.assertEqual(len(cloud.calls), 1)

    def test_selector_has_no_product_boundary_imports(self):
        source = Path("jarvis_core/voice/stt_selection.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

        forbidden = (
            "jarvis_core.runtime",
            "jarvis_core.planner",
            "jarvis_core.drivers",
            "jarvis_core.capabilities",
            "jarvis_core.api",
            "jarvis_core.dashboard",
        )
        self.assertFalse(
            any(module.startswith(forbidden) for module in imported_modules),
            imported_modules,
        )


def _fixture():
    return STTFixture(
        "selection_fixture",
        (FixtureCategory.MEXICAN_SPANISH,),
        "enciende la linterna",
        language_hint="es-MX",
        audio_reference="fixture.wav",
    )


if __name__ == "__main__":
    unittest.main()
