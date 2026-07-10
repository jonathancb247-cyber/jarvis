import unittest

from jarvis_core.domain import Command, Event, RuntimeContext


class DomainContractTest(unittest.TestCase):
    def test_command_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            Command(name="")

    def test_command_rejects_non_dict_args(self):
        with self.assertRaises(ValueError):
            Command(name="test.command", args=[])

    def test_command_rejects_empty_source(self):
        with self.assertRaises(ValueError):
            Command(name="test.command", source="")

    def test_event_rejects_non_dict_payload(self):
        with self.assertRaises(ValueError):
            Event(type="runtime.error", source="test", payload=[])

    def test_event_rejects_invalid_correlation_id(self):
        with self.assertRaises(ValueError):
            Event(type="runtime.error", source="test", correlation_id="")

    def test_event_rejects_invalid_causation_id(self):
        with self.assertRaises(ValueError):
            Event(type="runtime.error", source="test", causation_id="")

    def test_runtime_context_requires_event_bus(self):
        with self.assertRaises(ValueError):
            RuntimeContext(event_bus=None, capability_registry=object())

    def test_runtime_context_requires_capability_registry(self):
        with self.assertRaises(ValueError):
            RuntimeContext(event_bus=object(), capability_registry=None)

    def test_runtime_context_preserves_optional_device_registry(self):
        context = RuntimeContext(event_bus=object(), capability_registry=object())

        self.assertIsNone(context.device_registry)


if __name__ == "__main__":
    unittest.main()
