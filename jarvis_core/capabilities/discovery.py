"""Runtime capability for explicit simulated device discovery."""

from jarvis_core.discovery import (
    DiscoveryCandidate,
    DiscoveryCandidateStore,
    DiscoveryProviderUnavailable,
    DiscoveryScanError,
)
from jarvis_core.domain import CapabilityResult, Command


DEVICE_DISCOVERY_COMMAND = "device.discovery"
SCAN_OPERATION = "scan"

INVALID_DEVICE_DISCOVERY_COMMAND = "invalid_device_discovery_command"
UNSUPPORTED_DEVICE_DISCOVERY_OPERATION = "unsupported_device_discovery_operation"
DISCOVERY_PROVIDER_UNAVAILABLE = "discovery_provider_unavailable"
DISCOVERY_SCAN_FAILED = "discovery_scan_failed"
MALFORMED_DISCOVERY_CANDIDATE = "malformed_discovery_candidate"


class DeviceDiscoveryCapability:
    """Runtime Capability for explicit simulated discovery requests."""

    name = DEVICE_DISCOVERY_COMMAND

    def __init__(self, provider, candidate_store=None):
        self.provider = provider
        self.candidate_store = candidate_store

    def run(self, command, context):
        if not isinstance(command, Command) or command.name != self.name:
            return self._failure(
                INVALID_DEVICE_DISCOVERY_COMMAND,
                "Device discovery command is invalid.",
                {},
            )

        operation = command.args.get("operation")
        if operation != SCAN_OPERATION:
            return self._failure(
                UNSUPPORTED_DEVICE_DISCOVERY_OPERATION,
                "Device discovery command is invalid.",
                self._safe_data(operation),
            )

        if not callable(getattr(self.provider, "scan", None)):
            return self._failure(
                DISCOVERY_PROVIDER_UNAVAILABLE,
                "Discovery provider is unavailable.",
                self._safe_data(operation),
            )

        try:
            candidates = self.provider.scan()
        except DiscoveryProviderUnavailable:
            return self._failure(
                DISCOVERY_PROVIDER_UNAVAILABLE,
                "Discovery provider is unavailable.",
                self._safe_data(operation),
            )
        except DiscoveryScanError:
            return self._failure(
                DISCOVERY_SCAN_FAILED,
                "Discovery scan failed.",
                self._safe_data(operation),
            )
        except Exception:
            return self._failure(
                DISCOVERY_SCAN_FAILED,
                "Discovery scan failed.",
                self._safe_data(operation),
            )

        candidate_data = []
        validated_candidates = []
        for candidate in candidates:
            if not isinstance(candidate, DiscoveryCandidate):
                return self._failure(
                    MALFORMED_DISCOVERY_CANDIDATE,
                    "Discovery scan failed.",
                    self._safe_data(operation),
                )
            validated_candidates.append(candidate)
            candidate_data.append(self._candidate_data(candidate))

        if self.candidate_store is not None:
            if not isinstance(self.candidate_store, DiscoveryCandidateStore):
                return self._failure(
                    DISCOVERY_PROVIDER_UNAVAILABLE,
                    "Discovery provider is unavailable.",
                    self._safe_data(operation),
                )
            self.candidate_store.replace(validated_candidates)

        count = len(candidate_data)
        message = (
            "No discovery candidates found."
            if count == 0
            else "Discovery completed."
        )
        return CapabilityResult(
            success=True,
            message=message,
            data={
                "operation": SCAN_OPERATION,
                "count": count,
                "candidates": candidate_data,
            },
            error=None,
        )

    def _candidate_data(self, candidate):
        return {
            "candidate_id": candidate.candidate_id,
            "display_name": candidate.display_name,
            "transport": candidate.transport,
            "manufacturer": candidate.manufacturer,
            "model": candidate.model,
            "capability_hints": list(candidate.capability_hints),
        }

    def _safe_data(self, operation):
        data = {}
        if isinstance(operation, str) and operation:
            data["operation"] = operation
        return data

    def _failure(self, error, message, data):
        return CapabilityResult(
            success=False,
            message=message,
            data=data,
            error=error,
        )
