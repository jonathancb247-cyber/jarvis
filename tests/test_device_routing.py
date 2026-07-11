import unittest

from jarvis_core.device_routing import (
    CAPABILITY_NOT_FOUND_ERROR,
    DEVICE_NOT_FOUND,
    DRIVER_FAILURE,
    DRIVER_UNAVAILABLE_ERROR,
    INVALID_CAPABILITY_KIND_ERROR,
    INVALID_COMMAND,
    INVALID_COMMAND_ARGS,
    INVALID_PARAMETERS_ERROR,
    SIMULATED_TIMEOUT_ERROR,
    STATE_UPDATE_FAILED,
    DeviceCommandRouter,
    DeviceExecutionResult,
)
from jarvis_core.device_state import DeviceStateCoordinator
from jarvis_core.devices import Device, DeviceCapability, DeviceRegistry, DeviceState
from jarvis_core.domain import Command
from jarvis_core.drivers import DriverResult, SimulatedDriver


class TrackingDeviceRegistry(DeviceRegistry):
    def __init__(self):
        super().__init__()
        self.update_calls = []

    def update_state(self, device_id, state):
        self.update_calls.append((device_id, state))
        return super().update_state(device_id, state)


class RecordingDriver(SimulatedDriver):
    def __init__(self):
        super().__init__()
        self.calls = []

    def read(self, device, capability_name):
        self.calls.append(("read", device, capability_name))
        return super().read(device, capability_name)

    def apply(self, device, capability_name, parameters):
        self.calls.append(("apply", device, capability_name, parameters))
        return super().apply(device, capability_name, parameters)


class BrokenStateCoordinator(DeviceStateCoordinator):
    def coordinate(self, device, capability_name, operation, driver_result, registry):
        raise RuntimeError("broken")


class DeviceExecutionResultTests(unittest.TestCase):
    def test_valid_result(self):
        state = DeviceState(status="known", properties={"enabled": True})
        result = DeviceExecutionResult(
            success=True,
            device_id="device-1",
            capability="power.set",
            operation="apply",
            state=state,
            error=None,
            data={"device_id": "device-1"},
        )

        self.assertTrue(result.success)
        self.assertIs(result.state, state)

    def test_invalid_result_contract(self):
        invalid_results = [
            {"success": "yes"},
            {"device_id": ""},
            {"capability": ""},
            {"operation": "poll"},
            {"state": object()},
            {"error": ""},
            {"data": []},
        ]

        base = {
            "success": False,
            "device_id": "device-1",
            "capability": "power.set",
            "operation": "apply",
            "state": None,
            "error": "failed",
            "data": {},
        }
        for overrides in invalid_results:
            kwargs = base.copy()
            kwargs.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    DeviceExecutionResult(**kwargs)


class DeviceCommandRouterTests(unittest.TestCase):
    def make_device(self):
        return Device(
            id="device-1",
            name="Desk Lamp",
            type="light",
            capabilities=[
                DeviceCapability(name="temperature.read", kind="reading"),
                DeviceCapability(name="power.set", kind="action"),
                "legacy.power",
            ],
            state=DeviceState(status="unknown", properties={"enabled": False}),
        )

    def make_router(self, driver=None, coordinator=None):
        device = self.make_device()
        registry = TrackingDeviceRegistry()
        registry.register(device)
        driver = driver or RecordingDriver()
        coordinator = coordinator or DeviceStateCoordinator()
        return DeviceCommandRouter(registry, driver, coordinator), registry, driver, device

    def command(self, capability, operation, parameters=None, device_id="device-1"):
        args = {
            "device_id": device_id,
            "capability": capability,
            "operation": operation,
            "parameters": parameters or {},
        }
        return Command(name="device.execute", args=args, source="test")

    def test_successful_read_routes_to_driver_and_updates_state(self):
        router, registry, driver, device = self.make_router()
        driver.set_reading(device.id, "temperature.read", {"value": 23})

        result = router.route(self.command("temperature.read", "read"))

        self.assertTrue(result.success)
        self.assertEqual("device-1", result.device_id)
        self.assertEqual("temperature.read", result.capability)
        self.assertEqual("read", result.operation)
        self.assertEqual("known", result.state.status)
        self.assertEqual({"enabled": False, "value": 23}, result.state.properties)
        self.assertEqual([("read", device, "temperature.read")], driver.calls)
        self.assertEqual(1, len(registry.update_calls))

    def test_successful_apply_routes_to_driver_without_copying_parameters(self):
        router, registry, driver, device = self.make_router()

        result = router.route(
            self.command(
                "power.set",
                "apply",
                {"enabled": True, "secret": "do-not-copy"},
            )
        )

        self.assertTrue(result.success)
        self.assertIs(device.state, result.state)
        self.assertEqual({"enabled": False}, result.state.properties)
        self.assertEqual(
            [("apply", device, "power.set", {"enabled": True, "secret": "do-not-copy"})],
            driver.calls,
        )
        self.assertEqual(
            {
                "device_id": "device-1",
                "capability": "power.set",
                "operation": "apply",
            },
            result.data,
        )
        self.assertNotIn("parameters", result.data)
        self.assertEqual(0, len(registry.update_calls))

    def test_apply_with_driver_observation_updates_state(self):
        router, registry, _, _ = self.make_router()
        command = self.command("power.set", "apply")
        driver_result = DriverResult(True, {"enabled": True}, None)

        class ObservationDriver(SimulatedDriver):
            def apply(self, device, capability_name, parameters):
                return driver_result

        router.driver = ObservationDriver()

        result = router.route(command)

        self.assertTrue(result.success)
        self.assertEqual({"enabled": True}, result.state.properties)
        self.assertEqual(1, len(registry.update_calls))

    def test_invalid_command_object_returns_safe_error(self):
        router, _, _, _ = self.make_router()

        result = router.route(object())

        self.assertFalse(result.success)
        self.assertEqual(INVALID_COMMAND, result.error)
        self.assertEqual(
            {"device_id": "unknown", "capability": "unknown", "operation": "read"},
            result.data,
        )

    def test_wrong_command_name_returns_safe_error(self):
        router, _, _, _ = self.make_router()

        result = router.route(Command(name="time.now", source="test"))

        self.assertFalse(result.success)
        self.assertEqual(INVALID_COMMAND, result.error)
        self.assertNotIn("args", result.data)

    def test_invalid_args_shape_returns_safe_error(self):
        router, _, _, _ = self.make_router()

        result = router.route(Command(name="device.execute", args={}, source="test"))

        self.assertFalse(result.success)
        self.assertEqual(INVALID_COMMAND_ARGS, result.error)
        self.assertEqual("unknown", result.device_id)
        self.assertNotIn("args", result.data)

    def test_device_not_found(self):
        router, _, _, _ = self.make_router()

        result = router.route(
            self.command("temperature.read", "read", device_id="missing")
        )

        self.assertFalse(result.success)
        self.assertEqual(DEVICE_NOT_FOUND, result.error)

    def test_capability_not_found(self):
        router, registry, _, _ = self.make_router()

        result = router.route(self.command("humidity.read", "read"))

        self.assertFalse(result.success)
        self.assertEqual(CAPABILITY_NOT_FOUND_ERROR, result.error)
        self.assertEqual(0, len(registry.update_calls))

    def test_legacy_string_capability_is_not_executable(self):
        router, registry, _, _ = self.make_router()

        result = router.route(self.command("legacy.power", "apply"))

        self.assertFalse(result.success)
        self.assertEqual(CAPABILITY_NOT_FOUND_ERROR, result.error)
        self.assertEqual(0, len(registry.update_calls))

    def test_invalid_capability_kind(self):
        router, registry, _, _ = self.make_router()

        result = router.route(self.command("temperature.read", "apply"))

        self.assertFalse(result.success)
        self.assertEqual(INVALID_CAPABILITY_KIND_ERROR, result.error)
        self.assertEqual(0, len(registry.update_calls))

    def test_invalid_parameters(self):
        router, registry, _, _ = self.make_router()
        command = Command(
            name="device.execute",
            args={
                "device_id": "device-1",
                "capability": "power.set",
                "operation": "apply",
                "parameters": [],
            },
            source="test",
        )

        result = router.route(command)

        self.assertFalse(result.success)
        self.assertEqual(INVALID_PARAMETERS_ERROR, result.error)
        self.assertEqual(0, len(registry.update_calls))

    def test_driver_unavailable_updates_state_without_leaking_error_details(self):
        driver = RecordingDriver()
        driver.set_available(False)
        router, registry, _, _ = self.make_router(driver=driver)

        result = router.route(self.command("temperature.read", "read"))

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_UNAVAILABLE_ERROR, result.error)
        self.assertEqual("unavailable", result.state.status)
        self.assertEqual({"enabled": False}, result.state.properties)
        self.assertNotIn("error", result.data)
        self.assertEqual(1, len(registry.update_calls))

    def test_simulated_failure_returns_internal_failure(self):
        driver = RecordingDriver()
        driver.simulate_failure("read", "temperature.read")
        router, registry, _, _ = self.make_router(driver=driver)

        result = router.route(self.command("temperature.read", "read"))

        self.assertFalse(result.success)
        self.assertEqual(DRIVER_FAILURE, result.error)
        self.assertEqual(0, len(registry.update_calls))

    def test_simulated_timeout_returns_timeout_error(self):
        driver = RecordingDriver()
        driver.simulate_timeout("read", "temperature.read")
        router, _, _, _ = self.make_router(driver=driver)

        result = router.route(self.command("temperature.read", "read"))

        self.assertFalse(result.success)
        self.assertEqual(SIMULATED_TIMEOUT_ERROR, result.error)

    def test_state_update_failure_returns_safe_error(self):
        router, _, _, _ = self.make_router(coordinator=BrokenStateCoordinator())

        result = router.route(self.command("temperature.read", "read"))

        self.assertFalse(result.success)
        self.assertEqual(STATE_UPDATE_FAILED, result.error)
        self.assertNotIn("broken", result.data.values())

    def test_driver_does_not_receive_command(self):
        router, _, driver, _ = self.make_router()

        router.route(self.command("temperature.read", "read"))

        self.assertEqual(1, len(driver.calls))
        self.assertNotIsInstance(driver.calls[0][1], Command)

    def test_router_constructor_rejects_invalid_dependencies(self):
        registry = DeviceRegistry()
        driver = RecordingDriver()
        coordinator = DeviceStateCoordinator()

        with self.assertRaises(TypeError):
            DeviceCommandRouter(object(), driver, coordinator)
        with self.assertRaises(TypeError):
            DeviceCommandRouter(registry, object(), coordinator)
        with self.assertRaises(TypeError):
            DeviceCommandRouter(registry, driver, object())


if __name__ == "__main__":
    unittest.main()
