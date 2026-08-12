import json
import threading
import unittest

from jarvis_core.mqtt_driver import (
    MQTTClientClosedError,
    MQTTConnectionError,
    MQTTPublishError,
    MQTTTimeoutError,
)
from jarvis_core.mqtt_paho import PahoMQTTClient


class FakePublishInfo:
    def __init__(self, rc=0):
        self.rc = rc
        self.wait_count = 0

    def wait_for_publish(self, timeout=None):
        self.wait_count += 1
        return True


class FakePahoClient:
    def __init__(self):
        self.on_connect = None
        self.on_message = None
        self.on_disconnect = None
        self.connects = []
        self.loop_start_count = 0
        self.loop_stop_count = 0
        self.disconnect_count = 0
        self.subscriptions = []
        self.published = []
        self.publish_info = FakePublishInfo()
        self.subscribe_rc = 0
        self.connect_raises = None
        self.publish_raises = None

    def connect(self, host, port, keepalive):
        if self.connect_raises is not None:
            raise self.connect_raises
        self.connects.append((host, port, keepalive))

    def loop_start(self):
        self.loop_start_count += 1
        if self.on_connect is not None:
            self.on_connect(self, None, None, 0, None)

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))
        return (self.subscribe_rc, 1)

    def publish(self, topic, payload, qos=0, retain=False):
        if self.publish_raises is not None:
            raise self.publish_raises
        self.published.append((topic, payload, qos, retain))
        return self.publish_info

    def disconnect(self):
        self.disconnect_count += 1
        if self.on_disconnect is not None:
            self.on_disconnect(self, None, None, 0, None)

    def loop_stop(self):
        self.loop_stop_count += 1

    def emit(self, topic, payload):
        message = type("Message", (), {"topic": topic, "payload": payload})
        self.on_message(self, None, message)


class PahoMQTTClientTests(unittest.TestCase):
    def make_client(self, fake=None, response_topics=("jarvis/lab/lamp_1/response",)):
        fake = fake or FakePahoClient()
        client = PahoMQTTClient(
            host="127.0.0.1",
            port=1883,
            response_topics=response_topics,
            connect_timeout_seconds=0.1,
            client_factory=lambda client_id: fake,
            client_id="jarvisos-test",
        )
        return client, fake

    def test_rejects_non_loopback_host(self):
        with self.assertRaises(ValueError):
            PahoMQTTClient(host="192.168.1.10")

    def test_connect_subscribe_publish_and_close_lifecycle(self):
        client, fake = self.make_client()

        client.publish("jarvis/lab/lamp_1/request", b"{}")
        client.close()
        client.close()

        self.assertEqual(fake.connects, [("127.0.0.1", 1883, 30)])
        self.assertEqual(fake.loop_start_count, 1)
        self.assertEqual(fake.subscriptions, [("jarvis/lab/lamp_1/response", 0)])
        self.assertEqual(fake.published[0], ("jarvis/lab/lamp_1/request", b"{}", 0, False))
        self.assertEqual(fake.disconnect_count, 1)
        self.assertEqual(fake.loop_stop_count, 1)

    def test_matching_response_can_arrive_before_wait_call(self):
        client, fake = self.make_client()

        client.publish("jarvis/lab/lamp_1/request", b"{}")
        fake.emit(
            "jarvis/lab/lamp_1/response",
            json.dumps(
                {
                    "request_id": "req-1",
                    "ok": True,
                    "semantic": {"power": True},
                    "error": None,
                }
            ).encode("utf-8"),
        )
        response = client.wait_for_response(
            "jarvis/lab/lamp_1/response",
            "req-1",
            0.1,
        )

        self.assertEqual(
            json.loads(response.decode("utf-8"))["semantic"],
            {"power": True},
        )

    def test_wait_timeout_for_missing_or_wrong_correlation(self):
        client, fake = self.make_client()
        client.publish("jarvis/lab/lamp_1/request", b"{}")
        fake.emit(
            "jarvis/lab/lamp_1/response",
            b'{"request_id":"other","ok":true,"semantic":{"power":true},"error":null}',
        )

        with self.assertRaises(MQTTTimeoutError):
            client.wait_for_response("jarvis/lab/lamp_1/response", "req-1", 0.01)

    def test_invalid_json_message_does_not_satisfy_wait(self):
        client, fake = self.make_client()
        client.publish("jarvis/lab/lamp_1/request", b"{}")
        fake.emit("jarvis/lab/lamp_1/response", b"{")

        with self.assertRaises(MQTTTimeoutError):
            client.wait_for_response("jarvis/lab/lamp_1/response", "req-1", 0.01)

    def test_publish_and_subscribe_failures_are_safe(self):
        fake = FakePahoClient()
        fake.publish_info = FakePublishInfo(rc=1)
        client, _ = self.make_client(fake=fake)
        with self.assertRaises(MQTTPublishError):
            client.publish("jarvis/lab/lamp_1/request", b"{}")

        fake = FakePahoClient()
        fake.subscribe_rc = 1
        client, _ = self.make_client(fake=fake)
        with self.assertRaises(MQTTConnectionError):
            client.publish("jarvis/lab/lamp_1/request", b"{}")

    def test_close_prevents_future_publish(self):
        client, _ = self.make_client()
        client.close()

        with self.assertRaises(MQTTClientClosedError):
            client.publish("jarvis/lab/lamp_1/request", b"{}")

    def test_wait_blocks_until_callback_arrives(self):
        client, fake = self.make_client()
        client.publish("jarvis/lab/lamp_1/request", b"{}")

        def emit():
            fake.emit(
                "jarvis/lab/lamp_1/response",
                b'{"request_id":"req-1","ok":true,"semantic":{"power":false},"error":null}',
            )

        timer = threading.Timer(0.01, emit)
        timer.start()
        try:
            response = client.wait_for_response("jarvis/lab/lamp_1/response", "req-1", 0.2)
        finally:
            timer.cancel()

        self.assertEqual(json.loads(response.decode("utf-8"))["semantic"], {"power": False})


if __name__ == "__main__":
    unittest.main()
