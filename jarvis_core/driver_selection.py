"""Explicit per-device driver selection for profile composition."""

from jarvis_core.drivers import DRIVER_UNAVAILABLE, DriverResult


class DeviceTransportDriver:
    """Small composition-owned adapter that keeps Runtime transport-neutral."""

    def __init__(self):
        self._drivers = {}

    def register(self, device_id, driver):
        if not isinstance(device_id, str) or not device_id:
            raise ValueError("DeviceTransportDriver device_id must be a non-empty string")
        if device_id in self._drivers:
            raise ValueError(f"Driver already registered for device: {device_id}")
        if not callable(getattr(driver, "read", None)):
            raise TypeError("DeviceTransportDriver driver must define read")
        if not callable(getattr(driver, "apply", None)):
            raise TypeError("DeviceTransportDriver driver must define apply")
        self._drivers[device_id] = driver

    def read(self, device, capability_name):
        driver = self._driver_for(device)
        if driver is None:
            return DriverResult(False, {}, DRIVER_UNAVAILABLE)
        return driver.read(device, capability_name)

    def apply(self, device, capability_name, parameters):
        driver = self._driver_for(device)
        if driver is None:
            return DriverResult(False, {}, DRIVER_UNAVAILABLE)
        return driver.apply(device, capability_name, parameters)

    def close(self):
        closed = set()
        for driver in self._drivers.values():
            if id(driver) in closed:
                continue
            closed.add(id(driver))
            close = getattr(driver, "close", None)
            if callable(close):
                close()

    def _driver_for(self, device):
        device_id = getattr(device, "id", None)
        return self._drivers.get(device_id)
