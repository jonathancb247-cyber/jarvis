import unittest

from jarvis_core.capabilities.lifecycle import DeviceLifecycleRegistrar
from jarvis_core.capabilities.onboarding import (
    AUTHENTICATION_FAILED,
    CANDIDATE_NOT_FOUND,
    DEVICE_ONBOARDING_COMMAND,
    DUPLICATE_DEVICE,
    INVALID_DEVICE_ONBOARDING_COMMAND,
    LIFECYCLE_REGISTRATION_FAILED,
    MALFORMED_CANDIDATE,
    ONBOARDING_PROVIDER_UNAVAILABLE,
    PAIRING_FAILED,
    TRUST_REJECTED,
    DeviceOnboardingCapability,
)
from jarvis_core.devices import Device, DeviceRegistry
from jarvis_core.discovery import DiscoveryCandidate, DiscoveryCandidateStore
from jarvis_core.domain import CapabilityResult, Command, RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.onboarding import OnboardingProviderUnavailable, SimulatedOnboardingProvider
from jarvis_core.registry import CapabilityRegistry


class FailingRegistrar:
    def register(self, registry, device):
        raise RuntimeError("registration failed")


class RecordingRegistrar:
    def __init__(self):
        self.calls = []

    def register(self, registry, device):
        self.calls.append((registry, device))
        registry.register(device)
        return device


class UnavailableProvider:
    def pair(self, candidate):
        raise OnboardingProviderUnavailable()

    def authenticate(self, candidate):
        return True

    def trust(self, candidate):
        return True


class DeviceOnboardingCapabilityTests(unittest.TestCase):
    def build_context(self, registry=None):
        return RuntimeContext(
            event_bus=EventBus(),
            capability_registry=CapabilityRegistry(),
            device_registry=registry if registry is not None else DeviceRegistry(),
        )

    def candidate(self, candidate_id="candidate-1", display_name="Simulated Light"):
        return DiscoveryCandidate(
            candidate_id=candidate_id,
            display_name=display_name,
            transport="simulated",
            manufacturer="JarvisOS",
            model="SimulatedLight",
            capability_hints=["light", "power"],
        )

    def store_with_candidate(self, candidate=None):
        store = DiscoveryCandidateStore()
        store.replace([candidate if candidate is not None else self.candidate()])
        return store

    def command(self, candidate_id="candidate-1", device_id="lamp_1"):
        return Command(
            name=DEVICE_ONBOARDING_COMMAND,
            args={
                "operation": "approve",
                "candidate_id": candidate_id,
                "device_id": device_id,
            },
            source="cli",
        )

    def capability(self, store=None, provider=None, registrar=None):
        return DeviceOnboardingCapability(
            store if store is not None else self.store_with_candidate(),
            provider if provider is not None else SimulatedOnboardingProvider(),
            registrar if registrar is not None else DeviceLifecycleRegistrar(),
        )

    def test_successful_onboarding_registers_sanitized_device(self):
        registry = DeviceRegistry()
        store = self.store_with_candidate()

        result = self.capability(store=store).run(
            self.command(device_id="kitchen_lamp"),
            self.build_context(registry),
        )

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertEqual(result.message, "Device onboarded.")
        self.assertEqual(
            result.data,
            {"operation": "approve", "device_id": "kitchen_lamp", "registered": True},
        )
        self.assertIsNone(result.error)
        device = registry.get("kitchen_lamp")
        self.assertEqual(device.id, "kitchen_lamp")
        self.assertEqual(device.name, "Simulated Light")
        self.assertEqual(device.type, "generic")
        self.assertEqual(device.capabilities, [])
        self.assertEqual(device.state.status, "unknown")
        self.assertEqual(device.metadata, {})

    def test_candidate_missing(self):
        result = self.capability(store=DiscoveryCandidateStore()).run(
            self.command(),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, CANDIDATE_NOT_FOUND)
        self.assertEqual(result.message, "Discovery candidate not found.")

    def test_pairing_failure_preserves_candidate(self):
        store = self.store_with_candidate()

        result = self.capability(
            store=store,
            provider=SimulatedOnboardingProvider(pairing_success=False),
        ).run(self.command(), self.build_context())

        self.assertFalse(result.success)
        self.assertEqual(result.error, PAIRING_FAILED)
        self.assertEqual(result.message, "Device pairing failed.")
        self.assertEqual(len(store.list()), 1)

    def test_authentication_failure_preserves_candidate(self):
        store = self.store_with_candidate()

        result = self.capability(
            store=store,
            provider=SimulatedOnboardingProvider(authentication_success=False),
        ).run(self.command(), self.build_context())

        self.assertFalse(result.success)
        self.assertEqual(result.error, AUTHENTICATION_FAILED)
        self.assertEqual(result.message, "Device authentication failed.")
        self.assertEqual(len(store.list()), 1)

    def test_trust_rejected_preserves_candidate(self):
        store = self.store_with_candidate()

        result = self.capability(
            store=store,
            provider=SimulatedOnboardingProvider(trust_granted=False),
        ).run(self.command(), self.build_context())

        self.assertFalse(result.success)
        self.assertEqual(result.error, TRUST_REJECTED)
        self.assertEqual(result.message, "Device trust was not granted.")
        self.assertEqual(len(store.list()), 1)

    def test_duplicate_device_preserves_candidate(self):
        registry = DeviceRegistry()
        registry.register(Device(id="lamp_1", name="Lamp", type="light"))
        store = self.store_with_candidate()

        result = self.capability(store=store).run(
            self.command(),
            self.build_context(registry),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, DUPLICATE_DEVICE)
        self.assertEqual(result.message, "Device already exists.")
        self.assertEqual(len(store.list()), 1)

    def test_malformed_candidate(self):
        store = DiscoveryCandidateStore()
        store._candidates = {"candidate-1": object()}

        result = self.capability(store=store).run(
            self.command(),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, MALFORMED_CANDIDATE)

    def test_provider_unavailable(self):
        result = self.capability(provider=UnavailableProvider()).run(
            self.command(),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, ONBOARDING_PROVIDER_UNAVAILABLE)
        self.assertEqual(result.message, "Device onboarding provider is unavailable.")

    def test_lifecycle_registration_failure(self):
        result = self.capability(registrar=FailingRegistrar()).run(
            self.command(),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, LIFECYCLE_REGISTRATION_FAILED)
        self.assertEqual(result.message, "Device registration failed.")

    def test_invalid_command(self):
        result = self.capability().run(
            Command(name="wrong", args={}, source="cli"),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, INVALID_DEVICE_ONBOARDING_COMMAND)

    def test_invalid_args_are_safe(self):
        result = self.capability().run(
            Command(
                name=DEVICE_ONBOARDING_COMMAND,
                args={"operation": "approve", "candidate_id": "", "device_id": ""},
                source="cli",
            ),
            self.build_context(),
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, INVALID_DEVICE_ONBOARDING_COMMAND)
        self.assertNotIn("candidate_id", result.data)

    def test_sanitization_excludes_sensitive_fields(self):
        registry = DeviceRegistry()

        result = self.capability().run(self.command(), self.build_context(registry))

        self.assertTrue(result.success)
        output = str(result.data) + str(registry.get("lamp_1").metadata)
        for sensitive in [
            "mac",
            "ip",
            "serial",
            "fingerprint",
            "secret",
            "credential",
            "trust",
            "authentication",
            "pairing",
            "candidate-1",
            "light",
            "power",
        ]:
            self.assertNotIn(sensitive, output.lower())

    def test_candidate_consumed_after_success(self):
        store = self.store_with_candidate()

        result = self.capability(store=store).run(
            self.command(),
            self.build_context(),
        )

        self.assertTrue(result.success)
        self.assertEqual(store.list(), [])

    def test_candidate_id_is_not_device_id(self):
        registry = DeviceRegistry()

        result = self.capability().run(
            self.command(candidate_id="candidate-1", device_id="lamp_1"),
            self.build_context(registry),
        )

        self.assertTrue(result.success)
        self.assertTrue(registry.has("lamp_1"))
        self.assertFalse(registry.has("candidate-1"))

    def test_trust_does_not_enter_device_state(self):
        registry = DeviceRegistry()

        result = self.capability().run(self.command(), self.build_context(registry))

        self.assertTrue(result.success)
        state = registry.get("lamp_1").state
        self.assertEqual(state.status, "unknown")
        self.assertNotIn("trust", state.properties)

    def test_onboarding_uses_lifecycle_registrar(self):
        registrar = RecordingRegistrar()
        registry = DeviceRegistry()

        result = self.capability(registrar=registrar).run(
            self.command(),
            self.build_context(registry),
        )

        self.assertTrue(result.success)
        self.assertEqual(len(registrar.calls), 1)
        self.assertIs(registrar.calls[0][0], registry)


if __name__ == "__main__":
    unittest.main()
