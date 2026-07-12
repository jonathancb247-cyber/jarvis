import unittest

from jarvis_core.capabilities.discovery import (
    DISCOVERY_PROVIDER_UNAVAILABLE,
    DISCOVERY_SCAN_FAILED,
    INVALID_DEVICE_DISCOVERY_COMMAND,
    MALFORMED_DISCOVERY_CANDIDATE,
    UNSUPPORTED_DEVICE_DISCOVERY_OPERATION,
    DeviceDiscoveryCapability,
)
from jarvis_core.discovery import (
    DiscoveryCandidate,
    DiscoveryProviderUnavailable,
    DiscoveryScanError,
)
from jarvis_core.domain import CapabilityResult, Command, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.registry import CapabilityRegistry


class StaticProvider:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = 0

    def scan(self):
        self.calls += 1
        return self.candidates


class UnavailableProvider:
    def scan(self):
        raise DiscoveryProviderUnavailable()


class FailingProvider:
    def scan(self):
        raise DiscoveryScanError()


class DeviceDiscoveryCapabilityTests(unittest.TestCase):
    def context(self):
        return RuntimeContext(
            event_bus=EventBus(),
            capability_registry=CapabilityRegistry(),
            device_registry=None,
        )

    def command(self, operation="scan"):
        return Command(
            name="device.discovery",
            args={"operation": operation},
            source="test",
        )

    def test_successful_discovery(self):
        provider = StaticProvider(
            [
                DiscoveryCandidate(
                    candidate_id="candidate-1",
                    display_name="Simulated Light",
                    transport="simulated",
                    manufacturer="JarvisOS",
                    model="Light",
                    capability_hints=["light", "power"],
                )
            ]
        )
        result = DeviceDiscoveryCapability(provider).run(self.command(), self.context())

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertEqual(result.message, "Discovery completed.")
        self.assertIsNone(result.error)
        self.assertEqual(result.data["operation"], "scan")
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(
            result.data["candidates"],
            [
                {
                    "candidate_id": "candidate-1",
                    "display_name": "Simulated Light",
                    "transport": "simulated",
                    "manufacturer": "JarvisOS",
                    "model": "Light",
                    "capability_hints": ["light", "power"],
                }
            ],
        )

    def test_empty_discovery_is_success(self):
        result = DeviceDiscoveryCapability(StaticProvider([])).run(
            self.command(),
            self.context(),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.message, "No discovery candidates found.")
        self.assertEqual(result.data, {"operation": "scan", "count": 0, "candidates": []})

    def test_provider_unavailable(self):
        result = DeviceDiscoveryCapability(UnavailableProvider()).run(
            self.command(),
            self.context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, DISCOVERY_PROVIDER_UNAVAILABLE)
        self.assertEqual(result.message, "Discovery provider is unavailable.")

    def test_missing_provider_scan_is_unavailable(self):
        result = DeviceDiscoveryCapability(object()).run(
            self.command(),
            self.context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, DISCOVERY_PROVIDER_UNAVAILABLE)

    def test_scan_failure(self):
        result = DeviceDiscoveryCapability(FailingProvider()).run(
            self.command(),
            self.context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, DISCOVERY_SCAN_FAILED)
        self.assertEqual(result.message, "Discovery scan failed.")

    def test_malformed_candidate(self):
        result = DeviceDiscoveryCapability(StaticProvider([object()])).run(
            self.command(),
            self.context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, MALFORMED_DISCOVERY_CANDIDATE)
        self.assertEqual(result.message, "Discovery scan failed.")

    def test_sanitized_output_excludes_sensitive_fields(self):
        result = DeviceDiscoveryCapability(
            StaticProvider([DiscoveryCandidate("candidate-1", "Device", "simulated")])
        ).run(self.command(), self.context())

        candidate = result.data["candidates"][0]
        self.assertNotIn("mac", candidate)
        self.assertNotIn("ip", candidate)
        self.assertNotIn("serial", candidate)
        self.assertNotIn("fingerprint", candidate)
        self.assertNotIn("metadata", candidate)
        self.assertNotIn("credentials", candidate)

    def test_invalid_command(self):
        result = DeviceDiscoveryCapability(StaticProvider([])).run(
            Command(name="unknown", args={}, source="test"),
            self.context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, INVALID_DEVICE_DISCOVERY_COMMAND)

    def test_unsupported_operation(self):
        result = DeviceDiscoveryCapability(StaticProvider([])).run(
            self.command(operation="pair"),
            self.context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, UNSUPPORTED_DEVICE_DISCOVERY_OPERATION)


if __name__ == "__main__":
    unittest.main()
