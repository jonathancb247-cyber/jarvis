class Planner:
    def __init__(self, registry):
        self.registry = registry

    def plan(self, text):
        normalized = text.strip().lower()
        if "time" in normalized or "hora" in normalized:
            return "time.now"
        return "unknown"

    def execute(self, text):
        capability_name = self.plan(text)
        if capability_name == "unknown":
            return "I do not know how to handle that yet."
        capability = self.registry.resolve(capability_name)
        return capability.run()
