class CapabilityContractError(ValueError):
    """Raised when a capability does not satisfy the runtime contract."""


class CapabilityRegistry:
    def __init__(self):
        self.capabilities = {}

    def register(self, name, capability):
        self._validate_contract(name, capability)
        self.capabilities[name] = capability

    def resolve(self, name):
        if name not in self.capabilities:
            raise KeyError(f"Capability not found: {name}")
        return self.capabilities[name]

    def _validate_contract(self, name, capability):
        if not isinstance(name, str) or not name:
            raise CapabilityContractError("Capability name must be a non-empty string")
        if not hasattr(capability, "name"):
            raise CapabilityContractError("Capability must define name")
        if capability.name != name:
            raise CapabilityContractError("Capability name must match registry name")
        if not callable(getattr(capability, "run", None)):
            raise CapabilityContractError("Capability must define run(command, context)")
