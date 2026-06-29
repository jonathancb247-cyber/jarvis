import time as clock


class ClockCapability:
    name = "time.now"

    def run(self):
        value = clock.strftime("%H:%M")
        return "The current time is " + value + "."
