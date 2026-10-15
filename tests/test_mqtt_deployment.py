"""Tests for deployment-level MQTT broker configuration and LAN policy.

These tests deliberately use generic private LAN addresses rather than the
thesis lab broker address, so no real deployment address is committed.
"""

import unittest

from pathlib import Path

from jarvis_core.bootstrap import (
    _driver_from_profile,
    _resolve_mqtt_client,
)
from jarvis_core.configuration import RuntimeConfigurationLoader
from jarvis_core.driver_selection import DeviceTransportDriver
from jarvis_core.mqtt_deployment import (
    DEFAULT_BROKER_PORT,
    MQTTDeploymentConfig,
)
from jarvis_core.mqtt_driver import (
    MQTTDeviceBindingStore,
    MQTTDeviceDriver,
    UnavailableMQTTClient,
)
from jarvis_core.mqtt_paho import PahoMQTTClient

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_LAN_HOST = "192.168.1.50"
PRIVATE_LAN_HOST_2 = "10.0.0.5"
PUBLIC_HOST = "8.8.8.8"
PUBLIC_HOST_2 = "93.184.216.34"
# Documentation ranges are NOT publicly routable: Python's ipaddress reports
# them as private, so they are valid "not public" examples rather than public
# ones. They are asserted separately so that distinction stays explicit.
UNROUTABLE_DOC_HOST = "203.0.113.10"


def client_for(environ):
    """Resolve a client exactly as composition does, with an injected environ."""
    return _resolve_mqtt_client(None, environ=environ)


class MQTTDeploymentConfigTests(unittest.TestCase):
    def test_absent_host_is_unconfigured(self):
        self.assertIsNone(MQTTDeploymentConfig.from_environment(environ={}))

    def test_absent_host_keeps_unavailable_client(self):
        self.assertIsInstance(client_for({}), UnavailableMQTTClient)

    def test_unrelated_environment_keeps_unavailable_client(self):
        self.assertIsInstance(
            client_for({"PATH": "C:\\Windows", "HOME": "x"}),
            UnavailableMQTTClient,
        )

    def test_explicit_host_builds_real_client(self):
        client = client_for({"JARVIS_MQTT_HOST": "127.0.0.1"})
        self.assertIsInstance(client, PahoMQTTClient)
        self.assertEqual("127.0.0.1", client.host)
        self.assertEqual(DEFAULT_BROKER_PORT, client.port)
        self.assertFalse(client.allow_lan)

    def test_port_defaults_when_absent(self):
        config = MQTTDeploymentConfig.from_environment(
            environ={"JARVIS_MQTT_HOST": "127.0.0.1"}
        )
        self.assertEqual(DEFAULT_BROKER_PORT, config.port)

    def test_explicit_port_is_used(self):
        config = MQTTDeploymentConfig.from_environment(
            environ={"JARVIS_MQTT_HOST": "127.0.0.1", "JARVIS_MQTT_PORT": "1884"}
        )
        self.assertEqual(1884, config.port)

    def test_port_is_trimmed(self):
        config = MQTTDeploymentConfig.from_environment(
            environ={"JARVIS_MQTT_HOST": "127.0.0.1", "JARVIS_MQTT_PORT": " 1883 "}
        )
        self.assertEqual(1883, config.port)

    def test_private_lan_host_without_opt_in_is_rejected(self):
        with self.assertRaises(ValueError):
            client_for({"JARVIS_MQTT_HOST": PRIVATE_LAN_HOST})

    def test_private_lan_host_with_opt_in_is_allowed(self):
        client = client_for(
            {
                "JARVIS_MQTT_HOST": PRIVATE_LAN_HOST,
                "JARVIS_MQTT_PORT": "1883",
                "JARVIS_MQTT_ALLOW_LAN": "1",
            }
        )
        self.assertIsInstance(client, PahoMQTTClient)
        self.assertEqual(PRIVATE_LAN_HOST, client.host)
        self.assertEqual(1883, client.port)
        self.assertTrue(client.allow_lan)

    def test_second_private_lan_range_with_opt_in_is_allowed(self):
        client = client_for(
            {
                "JARVIS_MQTT_HOST": PRIVATE_LAN_HOST_2,
                "JARVIS_MQTT_ALLOW_LAN": "yes",
            }
        )
        self.assertTrue(client.allow_lan)

    def test_allow_lan_does_not_change_port_default(self):
        config = MQTTDeploymentConfig.from_environment(
            environ={"JARVIS_MQTT_HOST": PRIVATE_LAN_HOST, "JARVIS_MQTT_ALLOW_LAN": "true"}
        )
        self.assertEqual(DEFAULT_BROKER_PORT, config.port)

    def test_public_host_with_opt_in_is_rejected(self):
        with self.assertRaises(ValueError):
            client_for(
                {
                    "JARVIS_MQTT_HOST": PUBLIC_HOST,
                    "JARVIS_MQTT_ALLOW_LAN": "1",
                }
            )

    def test_public_host_without_opt_in_is_rejected(self):
        with self.assertRaises(ValueError):
            client_for({"JARVIS_MQTT_HOST": PUBLIC_HOST})

    def test_hostname_is_rejected(self):
        with self.assertRaises(ValueError):
            client_for(
                {"JARVIS_MQTT_HOST": "broker.example", "JARVIS_MQTT_ALLOW_LAN": "1"}
            )

    def test_empty_host_is_rejected(self):
        with self.assertRaises(ValueError):
            client_for({"JARVIS_MQTT_HOST": "   "})

    def test_host_with_outer_spaces_is_rejected(self):
        with self.assertRaises(ValueError):
            client_for({"JARVIS_MQTT_HOST": " 127.0.0.1"})

    def test_invalid_port_is_rejected(self):
        for bad_port in ("0", "-1", "70000", "abc", "18.83", "  "):
            with self.subTest(port=bad_port):
                with self.assertRaises(ValueError):
                    client_for(
                        {
                            "JARVIS_MQTT_HOST": "127.0.0.1",
                            "JARVIS_MQTT_PORT": bad_port,
                        }
                    )

    def test_invalid_allow_lan_value_is_rejected(self):
        with self.assertRaises(ValueError):
            client_for(
                {
                    "JARVIS_MQTT_HOST": PRIVATE_LAN_HOST,
                    "JARVIS_MQTT_ALLOW_LAN": "maybe",
                }
            )

    def test_allow_lan_falsy_values_do_not_authorize_lan(self):
        for value in ("0", "false", "no", "off", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    client_for(
                        {
                            "JARVIS_MQTT_HOST": PRIVATE_LAN_HOST,
                            "JARVIS_MQTT_ALLOW_LAN": value,
                        }
                    )

    def test_no_discovered_broker_is_ever_used(self):
        # Only these three variables may influence broker resolution.
        config = MQTTDeploymentConfig.from_environment(
            environ={
                "MQTT_HOST": PRIVATE_LAN_HOST,
                "BROKER_HOST": PUBLIC_HOST,
                "JARVIS_MQTT_HOST": "127.0.0.1",
            }
        )
        self.assertEqual("127.0.0.1", config.host)


class PahoBrokerHostPolicyTests(unittest.TestCase):
    def test_loopback_names_allowed_without_opt_in(self):
        for host in ("127.0.0.1", "localhost"):
            with self.subTest(host=host):
                client = PahoMQTTClient(host=host)
                self.assertEqual(host, client.host)
                self.assertFalse(client.allow_lan)

    def test_loopback_ip_range_allowed_without_opt_in(self):
        for host in ("127.0.0.2", "::1"):
            with self.subTest(host=host):
                PahoMQTTClient(host=host)

    def test_default_host_is_loopback(self):
        self.assertEqual("127.0.0.1", PahoMQTTClient().host)

    def test_private_lan_rejected_without_opt_in(self):
        with self.assertRaises(ValueError):
            PahoMQTTClient(host=PRIVATE_LAN_HOST)

    def test_private_lan_allowed_with_opt_in(self):
        client = PahoMQTTClient(host=PRIVATE_LAN_HOST, allow_lan=True)
        self.assertTrue(client.allow_lan)

    def test_link_local_host_requires_opt_in(self):
        with self.assertRaises(ValueError):
            PahoMQTTClient(host="169.254.10.10")
        client = PahoMQTTClient(host="169.254.10.10", allow_lan=True)
        self.assertTrue(client.allow_lan)

    def test_public_address_rejected_even_with_opt_in(self):
        for host in (PUBLIC_HOST, PUBLIC_HOST_2):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    PahoMQTTClient(host=host, allow_lan=True)

    def test_public_address_rejected_without_opt_in(self):
        with self.assertRaises(ValueError):
            PahoMQTTClient(host=PUBLIC_HOST)

    def test_unroutable_documentation_range_is_not_treated_as_public(self):
        # These addresses are not routable on the Internet, so LAN authorization
        # governs them instead of the public-address rejection rule.
        client = PahoMQTTClient(host=UNROUTABLE_DOC_HOST, allow_lan=True)
        self.assertTrue(client.allow_lan)

    def test_public_dns_name_rejected(self):
        with self.assertRaises(ValueError):
            PahoMQTTClient(host="mqtt.example.com", allow_lan=True)

    def test_empty_host_rejected(self):
        with self.assertRaises(ValueError):
            PahoMQTTClient(host="")

    def test_non_string_host_rejected(self):
        with self.assertRaises(ValueError):
            PahoMQTTClient(host=None)

    def test_invalid_port_still_rejected(self):
        for bad_port in (0, -1, 70000, "1883"):
            with self.subTest(port=bad_port):
                with self.assertRaises(ValueError):
                    PahoMQTTClient(host="127.0.0.1", port=bad_port)

    def test_response_validation_guards_unchanged(self):
        client = PahoMQTTClient(host="127.0.0.1")
        self.assertEqual(16384, client.max_response_bytes)


class ProfileWithoutBrokerFieldsTests(unittest.TestCase):
    def test_aligned_profile_loads_without_broker_fields(self):
        profile = RuntimeConfigurationLoader().load(
            REPO_ROOT / "profiles" / "mqtt-esp32.example.json"
        )
        self.assertEqual(1, profile.schema_version)
        self.assertEqual(["relay_1"], [device.id for device in profile.devices])

    def test_profile_declares_no_broker_field(self):
        profile = RuntimeConfigurationLoader().load(
            REPO_ROOT / "profiles" / "mqtt-esp32.example.json"
        )
        binding = profile.mqtt_bindings[0]
        for field in ("broker", "host", "port", "url", "broker_uri"):
            with self.subTest(field=field):
                self.assertFalse(hasattr(binding, field))

    def test_profile_binding_matches_validated_topics(self):
        profile = RuntimeConfigurationLoader().load(
            REPO_ROOT / "profiles" / "mqtt-esp32.example.json"
        )
        binding = profile.mqtt_bindings[0]
        self.assertEqual("jarvis/devices/relay_1/request", binding.request_topic)
        self.assertEqual("jarvis/devices/relay_1/response", binding.response_topic)
        self.assertEqual(("state",), binding.allowed_response_keys)
        self.assertEqual(("power.switch",), binding.allowed_capabilities)

    def test_profile_composes_mqtt_driver_with_injected_client(self):
        # An injected client keeps composition hermetic: the driver is built
        # without consulting the ambient environment.
        profile = RuntimeConfigurationLoader().load(
            REPO_ROOT / "profiles" / "mqtt-esp32.example.json"
        )
        driver = _driver_from_profile(profile, mqtt_client=UnavailableMQTTClient())
        self.assertIsInstance(driver, DeviceTransportDriver)


class ClientResolutionTests(unittest.TestCase):
    def test_injected_client_always_wins_over_environment(self):
        sentinel = object()
        resolved = _resolve_mqtt_client(sentinel, environ={"JARVIS_MQTT_HOST": PUBLIC_HOST})
        self.assertIs(sentinel, resolved)

    def test_http_only_profile_never_builds_an_mqtt_client(self):
        profile = RuntimeConfigurationLoader().load(
            REPO_ROOT / "profiles" / "http-lab.example.json"
        )
        driver = _driver_from_profile(profile)
        self.assertNotIsInstance(driver, MQTTDeviceDriver)

    def test_unavailable_client_surface_is_unchanged(self):
        client = UnavailableMQTTClient()
        self.assertTrue(callable(client.publish))
        self.assertTrue(callable(client.wait_for_response))
        self.assertTrue(callable(client.close))
        self.assertIsNone(client.close())

    def test_driver_defaults_to_unavailable_client_without_environment(self):
        store = MQTTDeviceBindingStore()
        driver = MQTTDeviceDriver(store)
        self.assertIsInstance(driver.client, UnavailableMQTTClient)


if __name__ == "__main__":
    unittest.main()