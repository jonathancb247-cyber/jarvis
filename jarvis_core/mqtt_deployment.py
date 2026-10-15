"""Deployment-level MQTT broker configuration for the thesis LAN integration.

Broker addressing is deployment/runtime infrastructure configuration. It is
deliberately NOT part of the declarative device profile: profiles describe
semantic devices and transport bindings, while the broker address belongs to
the environment where the Runtime happens to run.

Design boundary:

- Nothing is inferred. If no broker host is explicitly configured, this module
  reports "unconfigured" and composition keeps the fail-closed
  ``UnavailableMQTTClient``.
- No discovery. A broker is never located automatically.
- No cloud fallback and no provider registry.
- No credentials are read, stored, or logged here.
- No broker address is hardcoded in tracked source.

Environment variables:

``JARVIS_MQTT_HOST``
    Broker host. Required to enable a real MQTT client. Absent means the
    Runtime keeps its unavailable MQTT client.
``JARVIS_MQTT_PORT``
    Broker port. Optional; defaults to 1883 when the host is configured.
``JARVIS_MQTT_ALLOW_LAN``
    Explicit opt-in required before a non-loopback private LAN address may be
    used. Loopback never requires it.
"""

import os

from dataclasses import dataclass

MQTT_HOST_ENV = "JARVIS_MQTT_HOST"
MQTT_PORT_ENV = "JARVIS_MQTT_PORT"
MQTT_ALLOW_LAN_ENV = "JARVIS_MQTT_ALLOW_LAN"

DEFAULT_BROKER_PORT = 1883
MAX_PORT = 65535

TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
FALSY_VALUES = frozenset({"", "0", "false", "no", "off"})


@dataclass(frozen=True)
class MQTTDeploymentConfig:
    """Explicit broker deployment configuration."""

    host: str
    port: int = DEFAULT_BROKER_PORT
    allow_lan: bool = False

    @classmethod
    def from_environment(cls, environ=None):
        """Build broker config from the environment.

        Returns ``None`` when no broker host is explicitly configured, which
        keeps the existing fail-closed default. A configured-but-unparsable
        value (empty host, invalid port, non-boolean LAN flag) raises here
        instead of silently degrading to loopback or to no client; the broker
        address policy itself is enforced later by ``PahoMQTTClient``.
        """
        environ = os.environ if environ is None else environ
        raw_host = environ.get(MQTT_HOST_ENV)
        if raw_host is None:
            return None
        # The host is passed through untrimmed on purpose: the broker address
        # policy rejects outer whitespace instead of silently accepting a
        # padded value, which keeps environment configuration and direct
        # construction consistent.
        if not raw_host:
            # An explicitly empty host is a configuration mistake, not a
            # request to fall back to loopback.
            raise ValueError("MQTT broker host is configured but empty")
        host = raw_host
        port = _parse_port(environ.get(MQTT_PORT_ENV))
        allow_lan = _parse_allow_lan(environ.get(MQTT_ALLOW_LAN_ENV))
        return cls(host=host, port=port, allow_lan=allow_lan)


def _parse_port(raw_port):
    if raw_port is None:
        return DEFAULT_BROKER_PORT
    value = raw_port.strip()
    if not value:
        raise ValueError("MQTT broker port is configured but empty")
    try:
        port = int(value, 10)
    except ValueError:
        raise ValueError("MQTT broker port must be an integer") from None
    if port <= 0 or port > MAX_PORT:
        raise ValueError("MQTT broker port is invalid")
    return port


def _parse_allow_lan(raw_allow_lan):
    if raw_allow_lan is None:
        return False
    value = raw_allow_lan.strip().lower()
    if value in TRUTHY_VALUES:
        return True
    if value in FALSY_VALUES:
        return False
    raise ValueError("MQTT LAN authorization flag must be a boolean value")