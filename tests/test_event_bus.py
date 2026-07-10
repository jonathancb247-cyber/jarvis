import unittest

from jarvis_core.domain import Event
from jarvis_core.event_bus import EventBus


class EventBusTest(unittest.TestCase):
    def test_publish_event_returns_handler_results(self):
        bus = EventBus()
        bus.subscribe(
            "user.input.received",
            lambda event: event.payload["text"].upper(),
        )

        results = bus.publish(
            Event(
                type="user.input.received",
                source="test",
                payload={"text": "hello"},
            )
        )

        self.assertEqual(results, ["HELLO"])

    def test_publish_runs_handlers_in_subscription_order(self):
        bus = EventBus()
        calls = []
        bus.subscribe("runtime.error", lambda event: calls.append("first") or "first")
        bus.subscribe("runtime.error", lambda event: calls.append("second") or "second")

        results = bus.publish(Event(type="runtime.error", source="test"))

        self.assertEqual(calls, ["first", "second"])
        self.assertEqual(results, ["first", "second"])

    def test_publish_without_subscribers_returns_empty_list(self):
        bus = EventBus()

        results = bus.publish(Event(type="missing.event", source="test"))

        self.assertEqual(results, [])

    def test_publish_rejects_non_event(self):
        bus = EventBus()

        with self.assertRaises(TypeError):
            bus.publish("user.input.received")

    def test_subscribe_rejects_empty_event_type(self):
        bus = EventBus()

        with self.assertRaises(ValueError):
            bus.subscribe("", lambda event: None)

    def test_subscribe_rejects_non_string_event_type(self):
        bus = EventBus()

        with self.assertRaises(ValueError):
            bus.subscribe(None, lambda event: None)

    def test_subscribe_rejects_non_callable_handler(self):
        bus = EventBus()

        with self.assertRaises(TypeError):
            bus.subscribe("runtime.error", None)

    def test_publish_propagates_handler_exceptions(self):
        bus = EventBus()

        def fail(event):
            raise RuntimeError("handler failed")

        bus.subscribe("runtime.error", fail)

        with self.assertRaises(RuntimeError):
            bus.publish(Event(type="runtime.error", source="test"))

    def test_handler_receives_full_event(self):
        bus = EventBus()
        received = []
        event = Event(
            type="user.input.received",
            source="cli",
            payload={"text": "hello"},
            correlation_id="flow-1",
            causation_id="cause-1",
        )
        bus.subscribe("user.input.received", received.append)

        bus.publish(event)

        self.assertEqual(received, [event])
        self.assertEqual(received[0].type, "user.input.received")
        self.assertEqual(received[0].source, "cli")
        self.assertEqual(received[0].payload, {"text": "hello"})
        self.assertEqual(received[0].correlation_id, "flow-1")
        self.assertEqual(received[0].causation_id, "cause-1")

    def test_event_has_default_payload_and_timestamp(self):
        event = Event(type="runtime.error", source="test")

        self.assertEqual(event.payload, {})
        self.assertIsInstance(event.timestamp, str)
        self.assertTrue(event.timestamp)

    def test_event_rejects_empty_type(self):
        with self.assertRaises(ValueError):
            Event(type="", source="test")

    def test_event_rejects_empty_source(self):
        with self.assertRaises(ValueError):
            Event(type="runtime.error", source="")


if __name__ == "__main__":
    unittest.main()
