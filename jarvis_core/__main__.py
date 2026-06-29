from jarvis_core.event_bus import EventBus
from jarvis_core.planner import Planner
from jarvis_core.registry import CapabilityRegistry
from jarvis_core.capabilities.clock import ClockCapability


def build_runtime():
    bus = EventBus()
    registry = CapabilityRegistry()
    registry.register(ClockCapability.name, ClockCapability())
    planner = Planner(registry)

    def route(payload):
        return planner.execute(payload.get("text", ""))

    bus.subscribe("user.input", route)
    return bus


def main():
    bus = build_runtime()
    text = "what time is it?"
    response = bus.publish("user.input", {"text": text})[0]
    print("Jarvis AVP-001")
    print("jarvis> " + text)
    print("Jarvis: " + response)


if __name__ == "__main__":
    main()
