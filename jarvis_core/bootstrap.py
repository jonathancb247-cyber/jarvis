"""Explicit composition roots for JarvisOS runtimes."""

from pathlib import Path

from jarvis_core.capabilities.catalog import DeviceCatalogCapability
from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.capabilities.device import DeviceRuntimeCapability
from jarvis_core.capabilities.discovery import DeviceDiscoveryCapability
from jarvis_core.capabilities.lifecycle import (
    DeviceLifecycleCapability,
    DeviceLifecycleRegistrar,
)
from jarvis_core.capabilities.onboarding import DeviceOnboardingCapability
from jarvis_core.configuration import (
    RuntimeConfigurationLoader,
    build_devices,
    build_http_bindings,
    build_mqtt_bindings,
)
from jarvis_core.driver_selection import DeviceTransportDriver
from jarvis_core.device_routing import DeviceCommandRouter
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import DeviceRegistry
from jarvis_core.discovery import DiscoveryCandidateStore, SimulatedDiscoveryProvider
from jarvis_core.domain import RuntimeContext
from jarvis_core.drivers import SimulatedDriver
from jarvis_core.event_bus import EventBus
from jarvis_core.http_driver import (
    HttpDeviceBindingStore,
    HttpDeviceDriver,
    UrllibHttpJsonTransport,
)
from jarvis_core.mqtt_driver import (
    MQTTDeviceBindingStore,
    MQTTDeviceDriver,
    UnavailableMQTTClient,
)
from jarvis_core.onboarding import SimulatedOnboardingProvider
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.runtime import Runtime
from jarvis_core.state_store import (
    DeviceStatePersistence,
    JsonDeviceStateStore,
    PersistingDeviceStateCoordinator,
)


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


def build_runtime_from_config(path, http_transport=None, mqtt_client=None):
    """Build a Runtime from an explicit declarative configuration file."""
    config_path = Path(path)
    profile = RuntimeConfigurationLoader().load(config_path)
    return build_runtime_from_profile(
        profile,
        http_transport=http_transport,
        mqtt_client=mqtt_client,
        base_directory=config_path.parent,
    )


def build_runtime_from_profile(
    profile,
    http_transport=None,
    mqtt_client=None,
    state_store=None,
    base_directory=None,
):
    """Build a Runtime from a validated RuntimeProfile."""
    devices = build_devices(profile)
    driver = _driver_from_profile(
        profile,
        http_transport=http_transport,
        mqtt_client=mqtt_client,
    )
    state_store = state_store or _state_store_from_profile(profile, base_directory)
    return _build_runtime_with_driver(driver, devices=devices, state_store=state_store)


def _driver_from_profile(profile, http_transport=None, mqtt_client=None):
    http_binding_store = HttpDeviceBindingStore()
    for binding in build_http_bindings(profile):
        http_binding_store.register(binding)
    http_driver = HttpDeviceDriver(
        http_binding_store,
        transport=http_transport or UrllibHttpJsonTransport(),
    )

    mqtt_bindings = build_mqtt_bindings(profile)
    if not mqtt_bindings:
        return http_driver

    mqtt_binding_store = MQTTDeviceBindingStore()
    for binding in mqtt_bindings:
        mqtt_binding_store.register(binding)
    mqtt_driver = MQTTDeviceDriver(
        mqtt_binding_store,
        client=mqtt_client or UnavailableMQTTClient(),
    )

    driver = DeviceTransportDriver()
    for binding in http_binding_store.list():
        driver.register(binding.device_id, http_driver)
    for binding in mqtt_binding_store.list():
        driver.register(binding.device_id, mqtt_driver)
    return driver


def _build_runtime_with_driver(driver, devices=None, state_store=None):
    bus = EventBus()
    capability_registry = CapabilityRegistry()
    device_registry = DeviceRegistry()
    for device in devices or []:
        device_registry.register(device)

    persistence = None
    shutdown_hook = None
    if state_store is not None:
        persistence = DeviceStatePersistence(device_registry, state_store)
        persistence.restore()
        shutdown_hook = persistence.save_snapshot

    candidate_store = DiscoveryCandidateStore()
    discovery_provider = SimulatedDiscoveryProvider()
    onboarding_provider = SimulatedOnboardingProvider()
    lifecycle_registrar = DeviceLifecycleRegistrar()
    state_coordinator = DeviceStateCoordinator()
    if persistence is not None:
        state_coordinator = PersistingDeviceStateCoordinator(
            state_coordinator,
            persistence,
        )
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
    return Runtime(Planner(), context, shutdown_hook=shutdown_hook)


def _state_store_from_profile(profile, base_directory=None):
    state_store_path = profile.runtime_options.get("state_store_path")
    if not state_store_path or base_directory is None:
        return None
    path = Path(state_store_path)
    if not path.is_absolute():
        path = Path(base_directory) / path
    return JsonDeviceStateStore(path)
