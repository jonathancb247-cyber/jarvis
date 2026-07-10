from jarvis_core.domain import Event


class EventBus:
    def __init__(self):
        self.handlers = {}

    def subscribe(self, event_type, handler):
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("EventBus event_type must be a non-empty string")
        if not callable(handler):
            raise TypeError("EventBus handler must be callable")
        self.handlers.setdefault(event_type, []).append(handler)

    def publish(self, event):
        if not isinstance(event, Event):
            raise TypeError("EventBus.publish expects an Event")
        results = []
        for handler in self.handlers.get(event.type, []):
            results.append(handler(event))
        return results
