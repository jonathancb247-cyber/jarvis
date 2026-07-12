"""Experimental simulated onboarding boundary for JarvisOS."""

from dataclasses import dataclass, field

from jarvis_core.devices import DeviceState
from jarvis_core.discovery import DiscoveryCandidate


class OnboardingProviderUnavailable(Exception):
    """Raised when the simulated onboarding provider is unavailable."""


@dataclass
class DeviceRegistrationProposal:
    """Internal sanitized proposal for lifecycle device registration."""

    device_id: str
    name: str
    type: str
    capabilities: list = field(default_factory=list)
    state: DeviceState = field(default_factory=DeviceState)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.device_id, str) or not self.device_id:
            raise ValueError("DeviceRegistrationProposal device_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("DeviceRegistrationProposal name must be a non-empty string")
        if not isinstance(self.type, str) or not self.type:
            raise ValueError("DeviceRegistrationProposal type must be a non-empty string")
        if not isinstance(self.capabilities, list):
            raise ValueError("DeviceRegistrationProposal capabilities must be a list")
        if not isinstance(self.state, DeviceState):
            raise ValueError("DeviceRegistrationProposal state must be a DeviceState")
        if not isinstance(self.metadata, dict):
            raise ValueError("DeviceRegistrationProposal metadata must be a dict")


class SimulatedOnboardingProvider:
    """Experimental deterministic provider for simulated onboarding checks."""

    def __init__(
        self,
        available=True,
        pairing_success=True,
        authentication_success=True,
        trust_granted=True,
    ):
        for label, value in {
            "available": available,
            "pairing_success": pairing_success,
            "authentication_success": authentication_success,
            "trust_granted": trust_granted,
        }.items():
            if not isinstance(value, bool):
                raise ValueError(f"SimulatedOnboardingProvider {label} must be a bool")
        self.available = available
        self.pairing_success = pairing_success
        self.authentication_success = authentication_success
        self.trust_granted = trust_granted

    def pair(self, candidate):
        self._ensure_available()
        self._validate_candidate(candidate)
        return self.pairing_success

    def authenticate(self, candidate):
        self._ensure_available()
        self._validate_candidate(candidate)
        return self.authentication_success

    def trust(self, candidate):
        self._ensure_available()
        self._validate_candidate(candidate)
        return self.trust_granted

    def _ensure_available(self):
        if not self.available:
            raise OnboardingProviderUnavailable(
                "simulated onboarding provider unavailable"
            )

    def _validate_candidate(self, candidate):
        if not isinstance(candidate, DiscoveryCandidate):
            raise ValueError("SimulatedOnboardingProvider expects a DiscoveryCandidate")
