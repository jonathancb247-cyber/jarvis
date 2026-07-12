import unittest

from jarvis_core.discovery import (
    DiscoveryCandidate,
    DiscoveryProviderUnavailable,
    DiscoveryScanError,
    SimulatedDiscoveryProvider,
)


class DiscoveryCandidateTests(unittest.TestCase):
    def test_valid_candidate_is_immutable(self):
        candidate = DiscoveryCandidate(
            candidate_id="candidate-1",
            display_name="Simulated Sensor",
            transport="simulated",
            manufacturer="JarvisOS",
            model="Sensor",
            capability_hints=["temperature"],
        )

        self.assertEqual(candidate.candidate_id, "candidate-1")
        self.assertEqual(candidate.capability_hints, ("temperature",))
        with self.assertRaises(Exception):
            candidate.display_name = "Changed"

    def test_invalid_candidate_contract(self):
        invalid_cases = [
            {"candidate_id": "", "display_name": "Device", "transport": "simulated"},
            {"candidate_id": "id", "display_name": "", "transport": "simulated"},
            {"candidate_id": "id", "display_name": "Device", "transport": ""},
            {
                "candidate_id": "id",
                "display_name": "Device",
                "transport": "simulated",
                "manufacturer": "",
            },
            {
                "candidate_id": "id",
                "display_name": "Device",
                "transport": "simulated",
                "model": "",
            },
            {
                "candidate_id": "id",
                "display_name": "Device",
                "transport": "simulated",
                "capability_hints": "light",
            },
            {
                "candidate_id": "id",
                "display_name": "Device",
                "transport": "simulated",
                "capability_hints": [""],
            },
        ]

        for kwargs in invalid_cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    DiscoveryCandidate(**kwargs)


class SimulatedDiscoveryProviderTests(unittest.TestCase):
    def test_zero_candidates(self):
        provider = SimulatedDiscoveryProvider(candidates=[])

        self.assertEqual(provider.scan(), [])

    def test_multiple_candidates_are_deterministic(self):
        candidates = [
            DiscoveryCandidate("candidate-1", "Light", "simulated"),
            DiscoveryCandidate("candidate-2", "Sensor", "simulated"),
        ]
        provider = SimulatedDiscoveryProvider(candidates=candidates)

        self.assertEqual(provider.scan(), candidates)
        self.assertEqual(provider.scan(), candidates)

    def test_malformed_candidate_can_be_returned_for_boundary_tests(self):
        malformed = object()
        provider = SimulatedDiscoveryProvider(candidates=[malformed])

        self.assertEqual(provider.scan(), [malformed])

    def test_unavailable_provider_raises_structured_error(self):
        provider = SimulatedDiscoveryProvider(available=False)

        with self.assertRaises(DiscoveryProviderUnavailable):
            provider.scan()

    def test_scan_failure_raises_structured_error(self):
        provider = SimulatedDiscoveryProvider(fail_scan=True)

        with self.assertRaises(DiscoveryScanError):
            provider.scan()


if __name__ == "__main__":
    unittest.main()
