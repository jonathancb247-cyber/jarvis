"""Manual HTTP LED validation runtime for an ESP32 running JarvisOS protocol."""

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from jarvis_core.capabilities.catalog import DeviceCatalogCapability
from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.capabilities.device import DeviceRuntimeCapability
from jarvis_core.cli import run_cli
from jarvis_core.device_routing import DeviceCommandRouter
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.domain import RuntimeContext
from jarvis_core.event_bus import EventBus
from jarvis_core.http_driver import (
    HttpDeviceBinding,
    HttpDeviceBindingStore,
    HttpDeviceDriver,
    UrllibHttpJsonTransport,
)
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.runtime import Runtime


DEFAULT_BASE_URL = "http://10.255.108.33"
DEVICE_ID = "lamp_1"


def build_http_led_validation_runtime(base_url=DEFAULT_BASE_URL, transport=None):
    """Build an explicit runtime for manual ESP32 LED validation."""
    device_registry = DeviceRegistry()
    device_registry.register(_make_led_device())

    binding_store = HttpDeviceBindingStore()
    binding_store.register(HttpDeviceBinding(device_id=DEVICE_ID, base_url=base_url))

    http_transport = transport or UrllibHttpJsonTransport()
    http_driver = HttpDeviceDriver(binding_store, transport=http_transport)
    state_coordinator = DeviceStateCoordinator()
    device_router = DeviceCommandRouter(
        device_registry,
        http_driver,
        state_coordinator,
    )

    capability_registry = CapabilityRegistry()
    capability_registry.register(ClockCapability.name, ClockCapability())
    capability_registry.register(DeviceCatalogCapability.name, DeviceCatalogCapability())
    capability_registry.register(
        DeviceRuntimeCapability.name,
        DeviceRuntimeCapability(device_router),
    )

    context = RuntimeContext(
        event_bus=EventBus(),
        capability_registry=capability_registry,
        device_registry=device_registry,
    )
    return Runtime(Planner(), context)


def _make_led_device():
    return Device(
        id=DEVICE_ID,
        name="ESP32 LED",
        type="light",
        capabilities=[
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={
                    "state": {
                        "type": "string",
                        "required": True,
                    },
                },
            ),
            DeviceCapability(
                name="status.read",
                kind="reading",
                parameters={},
            ),
        ],
        state=DeviceState(status="unknown"),
        metadata={},
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run JarvisOS against an ESP32 LED over local HTTP."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"ESP32 base URL. Default: {DEFAULT_BASE_URL}",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    runtime = build_http_led_validation_runtime(base_url=args.base_url)
    print(f"HTTP LED validation runtime configured for {args.base_url}")
    print("Try:")
    print("  device apply lamp_1 power.switch state=true")
    print("  device read lamp_1 status.read")
    print("  device state lamp_1")
    print("  device apply lamp_1 power.switch state=false")
    run_cli(runtime)


if __name__ == "__main__":
    main()
