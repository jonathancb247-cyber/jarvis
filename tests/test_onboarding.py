import unittest

from jarvis_core.devices import DeviceState
from jarvis_core.discovery import DiscoveryCandidate
from jarvis_core.onboarding import (
    DeviceRegistrationProposal,
    OnboardingProviderUnavailable,
    SimulatedOnboardingProvider,
)


class DeviceRegistrationProposalTests(unittest.TestCase):
    def test_valid_proposal(self):
        state = DeviceState(status="unknown")

        proposal = DeviceRegistrationProposal(
            device_id="lamp_1",
            name="Lamp",
            type="generic",
            capabilities=[],
            state=state,
            metadata={},
        )

        self.assertEqual(proposal.device_id, "lamp_1")
        self.assertIs(proposal.state, state)

    def test_invalid_proposal_contract(self):
        invalid_cases = [
            {"device_id": "", "name": "Lamp", "type": "generic"},
            {"device_id": "lamp_1", "name": "", "type": "generic"},
            {"device_id": "lamp_1", "name": "Lamp", "type": ""},
            {
                "device_id": "lamp_1",
                "name": "Lamp",
                "type": "generic",
                "capabilities": {},
            },
            {
                "device_id": "lamp_1",
                "name": "Lamp",
                "type": "generic",
                "state": object(),
            },
            {
                "device_id": "lamp_1",
                "name": "Lamp",
                "type": "generic",
                "metadata": [],
            },
        ]

        for kwargs in invalid_cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    DeviceRegistrationProposal(**kwargs)


class SimulatedOnboardingProviderTests(unittest.TestCase):
    def candidate(self):
        return DiscoveryCandidate("candidate-1", "Device", "simulated")

    def test_pairing_success_and_failure(self):
        self.assertTrue(SimulatedOnboardingProvider().pair(self.candidate()))
        self.assertFalse(
            SimulatedOnboardingProvider(pairing_success=False).pair(self.candidate())
        )

    def test_authentication_success_and_failure(self):
        self.assertTrue(SimulatedOnboardingProvider().authenticate(self.candidate()))
        self.assertFalse(
            SimulatedOnboardingProvider(authentication_success=False).authenticate(
                self.candidate()
            )
        )

    def test_trust_accept_and_reject(self):
        self.assertTrue(SimulatedOnboardingProvider().trust(self.candidate()))
        self.assertFalse(
            SimulatedOnboardingProvider(trust_granted=False).trust(self.candidate())
        )

    def test_results_are_deterministic(self):
        provider = SimulatedOnboardingProvider(
            pairing_success=True,
            authentication_success=False,
            trust_granted=True,
        )

        self.assertEqual(provider.pair(self.candidate()), provider.pair(self.candidate()))
        self.assertEqual(
            provider.authenticate(self.candidate()),
            provider.authenticate(self.candidate()),
        )
        self.assertEqual(
            provider.trust(self.candidate()),
            provider.trust(self.candidate()),
        )

    def test_unavailable_provider_raises(self):
        provider = SimulatedOnboardingProvider(available=False)

        with self.assertRaises(OnboardingProviderUnavailable):
            provider.pair(self.candidate())

    def test_no_hardware_or_persistence_dependencies(self):
        provider = SimulatedOnboardingProvider()

        self.assertFalse(hasattr(provider, "driver"))
        self.assertFalse(hasattr(provider, "driver_registry"))
        self.assertFalse(hasattr(provider, "device_registry"))
        self.assertFalse(hasattr(provider, "storage"))


if __name__ == "__main__":
    unittest.main()
