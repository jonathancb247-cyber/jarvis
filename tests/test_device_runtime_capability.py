import unittest

from jarvis_core.capabilities.clock import ClockCapability
from jarvis_core.capabilities.device import (
    DEVICE_EXECUTION_FAILED,
    DEVICE_TIMEOUT,
    INVALID_DEVICE_COMMAND,
    DeviceRuntimeCapability,
)
from jarvis_core.device_routing import (
    CAPABILITY_NOT_FOUND_ERROR,
    DEVICE_NOT_FOUND,
    DRIVER_UNAVAILABLE_ERROR,
    STATE_UPDATE_FAILED,
    DeviceCommandRouter,
)
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.domain import CapabilityResult, Command, RuntimeContext
from jarvis_core.drivers import SimulatedDriver
from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.runtime import Runtime, build_runtime


class BrokenRouter:
    def route(self, command):
        return "not a device execution result"


class BrokenStateCoordinator(DeviceStateCoordinator):
    def coordinate(self, device, capability_name, operation, driver_result, registry):
        raise RuntimeError("secret failure")


class DeviceRuntimeCapabilityTests(unittest.TestCase):
    def make_device(self):
        return Device(
            id="device-1",
            name="Desk Lamp",
            type="light",
            capabilities=[
                DeviceCapability(name="temperature.read", kind="reading"),
                DeviceCapability(name="power.set", kind="action"),
            ],
            state=DeviceState(status="unknown", properties={"enabled": False}),
        )

    def make_capability(self, driver=None, coordinator=None):
        device = self.make_device()
        registry = DeviceRegistry()
        registry.register(device)
        driver = driver or SimulatedDriver()
        coordinator = coordinator or DeviceStateCoordinator()
        router = DeviceCommandRouter(registry, driver, coordinator)
        return DeviceRuntimeCapability(router), registry, driver, device

    def command(self, capability, operation, parameters=None, device_id="device-1"):
        return Command(
            name="device.execute",
            args={
                "device_id": device_id,
                "capability": capability,
                "operation": operation,
                "parameters": parameters or {},
            },
            source="test",
        )

    def test_capability_contract(self):
        capability, _, _, _ = self.make_capability()

        self.assertEqual("device.execute", capability.name)
        self.assertTrue(callable(capability.run))

    def test_constructor_requires_router(self):
        with self.assertRaises(TypeError):
            DeviceRuntimeCapability(object())

    def test_command_wrong_name_returns_safe_failure(self):
        capability, _, _, _ = self.make_capability()

        result = capability.run(Command(name="time.now", source="test"), None)

        self.assertFalse(result.success)
        self.assertEqual(INVALID_DEVICE_COMMAND, result.error)
        self.assertEqual("Device command is invalid.", result.message)
        self.assertEqual({"command": "time.now", "source": "test"}, result.data)

    def test_successful_read_returns_capability_result(self):
        capability, _, driver, _ = self.make_capability()
        driver.set_reading("device-1", "temperature.read", {"value": 23})

        result = capability.run(self.command("temperature.read", "read"), None)

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertEqual("Device reading completed.", result.message)
        self.assertIsNone(result.error)
        self.assertEqual("device-1", result.data["device_id"])
        self.assertEqual("temperature.read", result.data["capability"])
        self.assertEqual("read", result.data["operation"])
        self.assertEqual("known", result.data["state"]["status"])
        self.assertEqual(
            {"enabled": False, "value": 23},
            result.data["state"]["properties"],
        )

    def test_successful_apply_returns_capability_result_without_parameters(self):
        capability, _, _, _ = self.make_capability()

        result = capability.run(
            self.command(
                "power.set",
                "apply",
                {"enabled": True, "secret": "do-not-copy"},
            ),
            None,
        )

        self.assertTrue(result.success)
        self.assertEqual("Device action completed.", result.message)
        self.assertNotIn("parameters", str(result.data))
        self.assertNotIn("do-not-copy", str(result.data))

    def test_device_not_found(self):
        capability, _, _, _ = self.make_capability()

        result = capability.run(
            self.command("temperature.read", "read", device_id="missing"),
            None,
        )

        self.assertFalse(result.success)
        self.assertEqual(DEVICE_NOT_FOUND, result.error)
        self.assertEqual("Device not found.", result.message)

    def test_capability_not_found(self):
        capability, _, _, _ = self.make_capability()

        result = capability.run(self.command("humidity.read", "read"), None)

        self.assertFalse(result.success)
        self.assertEqual(CAPABILITY_NOT_FOUND_ERROR, result.error)
        self.assertEqual("Device capability not found.", result.message)

    def test_driver_unavailable(self):
        driver = SimulatedDriver(available=False)
        capability, _, _, _ = self.make_capability(driver=driver)

        result = capability.run(self.command("temperature.read", "read"), None)

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_UNAVAILABLE_ERROR, result.error)
        self.assertEqual("Device is unavailable.", result.message)

    def test_driver_failure_is_sanitized(self):
        driver = SimulatedDriver()
        driver.simulate_failure("read", "temperature.read", error="internal.secret")
        capability, _, _, _ = self.make_capability(driver=driver)

        result = capability.run(self.command("temperature.read", "read"), None)

        self.assertFalse(result.success)
        self.assertEqual(DEVICE_EXECUTION_FAILED, result.error)
        self.assertEqual("Device command failed.", result.message)
        self.assertNotIn("internal.secret", str(result.data))

    def test_simulated_timeout_is_normalized(self):
        driver = SimulatedDriver()
        driver.simulate_timeout("read", "temperature.read")
        capability, _, _, _ = self.make_capability(driver=driver)

        result = capability.run(self.command("temperature.read", "read"), None)

        self.assertFalse(result.success)
        self.assertEqual(DEVICE_TIMEOUT, result.error)
        self.assertEqual("Device command failed.", result.message)

    def test_state_update_failure_is_sanitized(self):
        capability, _, _, _ = self.make_capability(
            coordinator=BrokenStateCoordinator()
        )

        result = capability.run(self.command("temperature.read", "read"), None)

        self.assertFalse(result.success)
        self.assertEqual(STATE_UPDATE_FAILED, result.error)
        self.assertEqual("Device state could not be updated.", result.message)
        self.assertNotIn("secret failure", str(result.data))

    def test_invalid_router_result_is_sanitized(self):
        capability = DeviceRuntimeCapability(BrokenRouter())

        result = capability.run(self.command("temperature.read", "read"), None)

        self.assertFalse(result.success)
        self.assertEqual(DEVICE_EXECUTION_FAILED, result.error)
        self.assertEqual("Device command failed.", result.message)

    def test_runtime_executes_registered_device_capability_without_knowing_driver(self):
        capability, registry, _, _ = self.make_capability()
        capability_registry = CapabilityRegistry()
        capability_registry.register(ClockCapability.name, ClockCapability())
        capability_registry.register(capability.name, capability)
        context = RuntimeContext(
            event_bus=EventBus(),
            capability_registry=capability_registry,
            device_registry=registry,
        )
        runtime = Runtime(Planner(), context)

        result = runtime.execute(self.command("temperature.read", "read"))

        self.assertIsInstance(result, CapabilityResult)
        self.assertTrue(result.success)
        self.assertEqual("Device reading completed.", result.message)
        self.assertFalse(hasattr(runtime, "driver"))

    def test_clock_capability_coexists(self):
        runtime = build_runtime()

        result = runtime.execute(Command(name="time.now"))

        self.assertTrue(result.success)
        self.assertTrue(result.message.startswith("The current time is "))

    def test_build_runtime_registers_device_execute_capability(self):
        runtime = build_runtime()

        capability = runtime.context.capability_registry.resolve("device.execute")

        self.assertIsInstance(capability, DeviceRuntimeCapability)

    def test_planner_and_cli_are_not_required_for_device_command(self):
        capability, _, driver, _ = self.make_capability()
        driver.set_reading("device-1", "temperature.read", {"value": 21})

        result = capability.run(self.command("temperature.read", "read"), None)

        self.assertTrue(result.success)
        self.assertEqual("Device reading completed.", result.message)


if __name__ == "__main__":
    unittest.main()
