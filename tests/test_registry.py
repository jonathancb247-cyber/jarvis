import unittest

from jarvis_core.domain import CapabilityResult
from jarvis_core.registry import CapabilityContractError, CapabilityRegistry


class ValidCapability:
    name = "test.capability"

    def run(self, command, context):
        return CapabilityResult(success=True, message="ok")


class MissingNameCapability:
    def run(self, command, context):
        return CapabilityResult(success=True, message="ok")


class MissingRunCapability:
    name = "missing.run"


class CapabilityRegistryTest(unittest.TestCase):
    def test_resolve_registered_capability(self):
        registry = CapabilityRegistry()
        capability = ValidCapability()

        registry.register("test.capability", capability)

        self.assertIs(registry.resolve("test.capability"), capability)

    def test_register_rejects_empty_name(self):
        registry = CapabilityRegistry()

        with self.assertRaises(CapabilityContractError):
            registry.register("", ValidCapability())

    def test_register_rejects_non_string_name(self):
        registry = CapabilityRegistry()

        with self.assertRaises(CapabilityContractError):
            registry.register(None, ValidCapability())

    def test_register_rejects_capability_without_name(self):
        registry = CapabilityRegistry()

        with self.assertRaises(CapabilityContractError):
            registry.register("missing.name", MissingNameCapability())

    def test_register_rejects_capability_name_mismatch(self):
        registry = CapabilityRegistry()

        with self.assertRaises(CapabilityContractError):
            registry.register("other.capability", ValidCapability())

    def test_register_rejects_capability_without_run(self):
        registry = CapabilityRegistry()

        with self.assertRaises(CapabilityContractError):
            registry.register("missing.run", MissingRunCapability())

    def test_resolve_missing_capability_raises_key_error(self):
        registry = CapabilityRegistry()

        with self.assertRaises(KeyError):
            registry.resolve("missing.capability")


if __name__ == "__main__":
    unittest.main()
