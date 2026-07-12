"""Runtime capability for explicit simulated device onboarding."""

from jarvis_core.devices import Device, DeviceRegistry, DeviceState
from jarvis_core.discovery import DiscoveryCandidate, DiscoveryCandidateStore
from jarvis_core.domain import CapabilityResult, Command
from jarvis_core.onboarding import (
    DeviceRegistrationProposal,
    OnboardingProviderUnavailable,
)


DEVICE_ONBOARDING_COMMAND = "device.onboarding"
APPROVE_OPERATION = "approve"

INVALID_DEVICE_ONBOARDING_COMMAND = "invalid_device_onboarding_command"
CANDIDATE_NOT_FOUND = "candidate_not_found"
PAIRING_FAILED = "pairing_failed"
AUTHENTICATION_FAILED = "authentication_failed"
TRUST_REJECTED = "trust_rejected"
DUPLICATE_DEVICE = "duplicate_device"
LIFECYCLE_REGISTRATION_FAILED = "lifecycle_registration_failed"
MALFORMED_CANDIDATE = "malformed_candidate"
ONBOARDING_PROVIDER_UNAVAILABLE = "onboarding_provider_unavailable"


class DeviceOnboardingCapability:
    """Runtime Capability for explicit simulated onboarding requests."""

    name = DEVICE_ONBOARDING_COMMAND

    def __init__(self, candidate_store, provider, registrar):
        self.candidate_store = candidate_store
        self.provider = provider
        self.registrar = registrar

    def run(self, command, context):
        if not isinstance(command, Command) or command.name != self.name:
            return self._failure(
                INVALID_DEVICE_ONBOARDING_COMMAND,
                "Device onboarding command is invalid.",
                {},
            )

        operation = command.args.get("operation")
        candidate_id = command.args.get("candidate_id")
        device_id = command.args.get("device_id")
        if (
            operation != APPROVE_OPERATION
            or not self._is_non_empty_string(candidate_id)
            or not self._is_non_empty_string(device_id)
        ):
            return self._failure(
                INVALID_DEVICE_ONBOARDING_COMMAND,
                "Device onboarding command is invalid.",
                self._safe_command_data(command),
            )

        if not isinstance(self.candidate_store, DiscoveryCandidateStore):
            return self._failure(
                CANDIDATE_NOT_FOUND,
                "Discovery candidate not found.",
                self._safe_command_data(command),
            )

        try:
            candidate = self.candidate_store.get(candidate_id)
        except (KeyError, ValueError):
            return self._failure(
                CANDIDATE_NOT_FOUND,
                "Discovery candidate not found.",
                self._safe_command_data(command),
            )

        if not isinstance(candidate, DiscoveryCandidate):
            return self._failure(
                MALFORMED_CANDIDATE,
                "Device registration failed.",
                self._safe_command_data(command),
            )

        if not self._has_provider_contract():
            return self._failure(
                ONBOARDING_PROVIDER_UNAVAILABLE,
                "Device onboarding provider is unavailable.",
                self._safe_command_data(command),
            )

        try:
            if not self.provider.pair(candidate):
                return self._failure(
                    PAIRING_FAILED,
                    "Device pairing failed.",
                    self._safe_command_data(command),
                )
            if not self.provider.authenticate(candidate):
                return self._failure(
                    AUTHENTICATION_FAILED,
                    "Device authentication failed.",
                    self._safe_command_data(command),
                )
            if not self.provider.trust(candidate):
                return self._failure(
                    TRUST_REJECTED,
                    "Device trust was not granted.",
                    self._safe_command_data(command),
                )
        except OnboardingProviderUnavailable:
            return self._failure(
                ONBOARDING_PROVIDER_UNAVAILABLE,
                "Device onboarding provider is unavailable.",
                self._safe_command_data(command),
            )
        except Exception:
            return self._failure(
                ONBOARDING_PROVIDER_UNAVAILABLE,
                "Device onboarding provider is unavailable.",
                self._safe_command_data(command),
            )

        try:
            proposal = self._build_proposal(candidate, device_id)
            registry = getattr(context, "device_registry", None)
            if not isinstance(registry, DeviceRegistry):
                raise TypeError("device registry unavailable")
            device = self._device_from_proposal(proposal)
            self.registrar.register(registry, device)
        except ValueError:
            return self._failure(
                DUPLICATE_DEVICE,
                "Device already exists.",
                self._safe_command_data(command),
            )
        except Exception:
            return self._failure(
                LIFECYCLE_REGISTRATION_FAILED,
                "Device registration failed.",
                self._safe_command_data(command),
            )

        self._consume_candidate(candidate_id)
        return CapabilityResult(
            success=True,
            message="Device onboarded.",
            data={
                "operation": APPROVE_OPERATION,
                "device_id": device_id,
                "registered": True,
            },
            error=None,
        )

    def _build_proposal(self, candidate, device_id):
        return DeviceRegistrationProposal(
            device_id=device_id,
            name=candidate.display_name.strip(),
            type="generic",
            capabilities=[],
            state=DeviceState(status="unknown"),
            metadata={},
        )

    def _device_from_proposal(self, proposal):
        return Device(
            id=proposal.device_id,
            name=proposal.name,
            type=proposal.type,
            capabilities=proposal.capabilities,
            state=proposal.state,
            metadata=proposal.metadata,
        )

    def _consume_candidate(self, candidate_id):
        remaining = [
            candidate
            for candidate in self.candidate_store.list()
            if candidate.candidate_id != candidate_id
        ]
        self.candidate_store.replace(remaining)

    def _has_provider_contract(self):
        return (
            callable(getattr(self.provider, "pair", None))
            and callable(getattr(self.provider, "authenticate", None))
            and callable(getattr(self.provider, "trust", None))
            and callable(getattr(self.registrar, "register", None))
        )

    def _safe_command_data(self, command):
        data = {}
        operation = command.args.get("operation")
        device_id = command.args.get("device_id")
        if isinstance(operation, str) and operation:
            data["operation"] = operation
        if isinstance(device_id, str) and device_id:
            data["device_id"] = device_id
        return data

    def _failure(self, error, message, data):
        return CapabilityResult(
            success=False,
            message=message,
            data=data,
            error=error,
        )

    def _is_non_empty_string(self, value):
        return isinstance(value, str) and bool(value)
