"""Paho-backed MQTT request/response client adapter for local validation."""

import ipaddress
import json
import threading
import time
from uuid import uuid4

from jarvis_core.mqtt_driver import (
    MAX_RESPONSE_BYTES,
    MAX_TOPIC_LENGTH,
    MQTTClientClosedError,
    MQTTConnectionError,
    MQTTPublishError,
    MQTTTimeoutError,
)


LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_BROKER_PORT = 1883
DEFAULT_KEEPALIVE_SECONDS = 30
MAX_CLIENT_ID_LENGTH = 80


class PahoMQTTClient:
    """Synchronous request/response adapter around paho-mqtt.

    This class implements the tiny client surface consumed by MQTTDeviceDriver:
    publish(), wait_for_response(), and close(). It owns all Paho callbacks and
    network-loop lifecycle internally.
    """

    def __init__(
        self,
        host="127.0.0.1",
        port=DEFAULT_BROKER_PORT,
        response_topics=(),
        connect_timeout_seconds=5.0,
        keepalive_seconds=DEFAULT_KEEPALIVE_SECONDS,
        max_response_bytes=MAX_RESPONSE_BYTES,
        client_factory=None,
        client_id=None,
        allow_lan=False,
    ):
        _validate_broker_host(host, allow_lan=allow_lan)
        if not isinstance(port, int) or port <= 0 or port > 65535:
            raise ValueError("PahoMQTTClient port is invalid")
        if connect_timeout_seconds <= 0:
            raise ValueError("PahoMQTTClient connect timeout is invalid")
        if keepalive_seconds <= 0:
            raise ValueError("PahoMQTTClient keepalive is invalid")
        if not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
            raise ValueError("PahoMQTTClient response limit is invalid")
        self.host = host
        self.port = port
        self.allow_lan = bool(allow_lan)
        self.connect_timeout_seconds = float(connect_timeout_seconds)
        self.keepalive_seconds = int(keepalive_seconds)
        self.max_response_bytes = max_response_bytes
        self.client_factory = client_factory
        self.client_id = client_id or f"jarvisos-mqtt-{uuid4().hex}"
        if len(self.client_id) > MAX_CLIENT_ID_LENGTH:
            raise ValueError("PahoMQTTClient client_id is too long")
        self._response_topics = tuple(response_topics)
        for topic in self._response_topics:
            _validate_topic(topic)
        self._client = None
        self._connected = threading.Event()
        self._condition = threading.Condition()
        self._pending = {}
        self._subscribed_topics = set()
        self._closed = False
        self._loop_started = False

    def publish(self, topic, payload):
        """Publish a bounded MQTT request payload."""
        if self._closed:
            raise MQTTClientClosedError()
        _validate_topic(topic)
        if not isinstance(payload, bytes):
            raise MQTTPublishError()
        client = self._ensure_connected()
        try:
            info = client.publish(topic, payload, qos=0, retain=False)
        except Exception as error:
            raise MQTTPublishError() from error
        rc = getattr(info, "rc", 0)
        if rc != 0:
            raise MQTTPublishError()
        wait_for_publish = getattr(info, "wait_for_publish", None)
        if callable(wait_for_publish):
            try:
                wait_for_publish(timeout=self.connect_timeout_seconds)
            except TypeError:
                wait_for_publish()
            except Exception as error:
                raise MQTTPublishError() from error

    def wait_for_response(self, topic, correlation_id, timeout_seconds):
        """Wait for the exact response topic and correlation ID."""
        if self._closed:
            raise MQTTClientClosedError()
        _validate_topic(topic)
        if not isinstance(correlation_id, str) or not correlation_id:
            raise MQTTConnectionError()
        if timeout_seconds <= 0:
            raise MQTTTimeoutError()
        self._ensure_connected()
        self._subscribe(topic)
        key = (topic, correlation_id)
        deadline = time.monotonic() + float(timeout_seconds)
        with self._condition:
            if key in self._pending:
                return self._pending.pop(key)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MQTTTimeoutError()
                self._condition.wait(remaining)
                if key in self._pending:
                    return self._pending.pop(key)

    def close(self):
        """Disconnect and stop the Paho network loop exactly once."""
        if self._closed:
            return None
        self._closed = True
        client = self._client
        if client is None:
            return None
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass
        return None

    def _ensure_connected(self):
        if self._closed:
            raise MQTTClientClosedError()
        if self._client is not None and self._connected.is_set():
            return self._client
        client = self._client or self._create_client()
        self._client = client
        try:
            client.connect(
                self.host,
                self.port,
                keepalive=self.keepalive_seconds,
            )
            client.loop_start()
            self._loop_started = True
        except Exception as error:
            raise MQTTConnectionError() from error
        if not self._connected.wait(self.connect_timeout_seconds):
            raise MQTTConnectionError()
        for topic in self._response_topics:
            self._subscribe(topic)
        return client

    def _create_client(self):
        if self.client_factory is not None:
            client = self.client_factory(self.client_id)
        else:
            import paho.mqtt.client as mqtt

            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.client_id,
            )
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        return client

    def _subscribe(self, topic):
        if topic in self._subscribed_topics:
            return
        try:
            result = self._client.subscribe(topic, qos=0)
        except Exception as error:
            raise MQTTConnectionError() from error
        rc = result[0] if isinstance(result, tuple) else getattr(result, "rc", 0)
        if rc != 0:
            raise MQTTConnectionError()
        self._subscribed_topics.add(topic)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if _is_success_reason(reason_code):
            self._connected.set()

    def _on_disconnect(self, client, userdata, flags=None, reason_code=None, properties=None):
        self._connected.clear()

    def _on_message(self, client, userdata, message):
        topic = getattr(message, "topic", None)
        payload = getattr(message, "payload", None)
        if not isinstance(topic, str) or not isinstance(payload, bytes):
            return
        if len(payload) > self.max_response_bytes:
            return
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except Exception:
            return
        if not isinstance(decoded, dict):
            return
        request_id = decoded.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            return
        with self._condition:
            self._pending[(topic, request_id)] = payload
            self._condition.notify_all()


def _validate_broker_host(host, allow_lan=False):
    """Fail-closed broker address policy.

    Loopback is always allowed. A private/link-local LAN address requires
    explicit opt-in through ``allow_lan``. Public Internet addresses are
    rejected outright in this phase, and hostnames are rejected because they
    cannot be classified without DNS resolution or discovery.
    """
    if not isinstance(host, str) or not host:
        raise ValueError("PahoMQTTClient host must be a non-empty string")
    if host.strip() != host:
        raise ValueError("PahoMQTTClient host must not have outer spaces")
    if host in LOOPBACK_HOSTS:
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError(
            "PahoMQTTClient host must be a loopback name or a literal IP address"
        ) from None
    if address.is_loopback:
        return None
    if address.is_global or not (address.is_private or address.is_link_local):
        raise ValueError("PahoMQTTClient host must not be a public Internet address")
    if not allow_lan:
        raise ValueError("PahoMQTTClient LAN host requires explicit LAN authorization")
    return None


def _is_success_reason(reason_code):
    if reason_code == 0:
        return True
    value = getattr(reason_code, "value", None)
    if value == 0:
        return True
    return str(reason_code).lower() in {"success", "0"}


def _validate_topic(topic):
    if not isinstance(topic, str) or not topic:
        raise ValueError("MQTT topic must be a non-empty string")
    if topic.strip() != topic:
        raise ValueError("MQTT topic must not have outer spaces")
    if len(topic) > MAX_TOPIC_LENGTH:
        raise ValueError("MQTT topic is too long")
    if "#" in topic or "+" in topic:
        raise ValueError("MQTT topic must not contain wildcards")
    if any(ord(character) < 32 or ord(character) == 127 for character in topic):
        raise ValueError("MQTT topic must not contain control characters")
