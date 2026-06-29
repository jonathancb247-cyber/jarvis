class EventBus:
    def __init__(self):
        self.handlers = {}

    def subscribe(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def publish(self, event_name, payload=None):
        payload = payload or {}
        results = []
        for handler in self.handlers.get(event_name, []):
            results.append(handler(payload))
        return results
