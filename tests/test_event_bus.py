import unittest

from jarvis_core.event_bus import EventBus


class EventBusTest(unittest.TestCase):
    def test_publish_returns_handler_results(self):
        bus = EventBus()
        bus.subscribe("user.input", lambda payload: payload["text"].upper())

        results = bus.publish("user.input", {"text": "hello"})

        self.assertEqual(results, ["HELLO"])

    def test_publish_without_subscribers_returns_empty_list(self):
        bus = EventBus()

        results = bus.publish("missing.event", {"text": "hello"})

        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
