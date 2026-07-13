"""Explicit composition roots for JarvisOS runtimes."""

from jarvis_core.capabilities.catalog import DeviceCatalogCapability
from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.capabilities.device import DeviceRuntimeCapability
from jarvis_core.capabilities.discovery import DeviceDiscoveryCapability
from jarvis_core.capabilities.lifecycle import (
    DeviceLifecycleCapability,
    DeviceLifecycleRegistrar,
)
from jarvis_core.capabilities.onboarding import DeviceOnboardingCapability
from jarvis_core.device_routing import DeviceCommandRouter
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import DeviceRegistry
from jarvis_core.discovery import DiscoveryCandidateStore, SimulatedDiscoveryProvider
from jarvis_core.domain import RuntimeContext
from jarvis_core.drivers import SimulatedDriver
from jarvis_core.event_bus import EventBus
from jarvis_core.onboarding import SimulatedOnboardingProvider
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.runtime import Runtime


def build_runtime():
    """Build the default safe AVP-001 runtime with simulated device driver."""
    return build_simulated_runtime()


def build_simulated_runtime():
    """Build the default in-memory runtime used by AVP-001."""
    return _build_runtime_with_driver(SimulatedDriver())


def build_http_runtime(driver, devices=None):
    """Build an explicit HTTP test/runtime profile with caller-provided driver."""
    if not callable(getattr(driver, "read", None)):
        raise TypeError("build_http_runtime driver must define read")
    if not callable(getattr(driver, "apply", None)):
        raise TypeError("build_http_runtime driver must define apply")
    return _build_runtime_with_driver(driver, devices=devices)


def _build_runtime_with_driver(driver, devices=None):
    bus = EventBus()
    capability_registry = CapabilityRegistry()
    device_registry = DeviceRegistry()
    for device in devices or []:
        device_registry.register(device)

    candidate_store = DiscoveryCandidateStore()
    discovery_provider = SimulatedDiscoveryProvider()
    onboarding_provider = SimulatedOnboardingProvider()
    lifecycle_registrar = DeviceLifecycleRegistrar()
    state_coordinator = DeviceStateCoordinator()
    device_router = DeviceCommandRouter(
        device_registry,
        driver,
        state_coordinator,
    )

    capability_registry.register(ClockCapability.name, ClockCapability())
    capability_registry.register(
        DeviceCatalogCapability.name,
        DeviceCatalogCapability(),
    )
    capability_registry.register(
        DeviceDiscoveryCapability.name,
        DeviceDiscoveryCapability(discovery_provider, candidate_store),
    )
    capability_registry.register(
        DeviceLifecycleCapability.name,
        DeviceLifecycleCapability(lifecycle_registrar),
    )
    capability_registry.register(
        DeviceOnboardingCapability.name,
        DeviceOnboardingCapability(
            candidate_store,
            onboarding_provider,
            lifecycle_registrar,
        ),
    )
    capability_registry.register(
        DeviceRuntimeCapability.name,
        DeviceRuntimeCapability(device_router),
    )

    context = RuntimeContext(
        event_bus=bus,
        capability_registry=capability_registry,
        device_registry=device_registry,
    )
    return Runtime(Planner(), context)
