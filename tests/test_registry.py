import unittest

from jarvis_core.registry import CapabilityRegistry


class CapabilityRegistryTest(unittest.TestCase):
    def test_resolve_registered_capability(self):
        registry = CapabilityRegistry()
        capability = object()

        registry.register("test.capability", capability)

        self.assertIs(registry.resolve("test.capability"), capability)

    def test_resolve_missing_capability_raises_key_error(self):
        registry = CapabilityRegistry()

        with self.assertRaises(KeyError):
            registry.resolve("missing.capability")


if __name__ == "__main__":
    unittest.main()
