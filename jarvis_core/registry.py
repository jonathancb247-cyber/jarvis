class CapabilityRegistry:
    def __init__(self):
        self.capabilities = {}

    def register(self, name, capability):
        self.capabilities[name] = capability

    def resolve(self, name):
        if name not in self.capabilities:
            raise KeyError(f"Capability not found: {name}")
        return self.capabilities[name]
