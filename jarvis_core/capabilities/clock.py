import time as clock

from jarvis_core.domain import CapabilityResult


class ClockCapability:
    name = "time.now"

    def run(self, command=None, context=None):
        value = clock.strftime("%H:%M")
        return CapabilityResult(
            success=True,
            message="The current time is " + value + ".",
            data={"time": value},
        )
