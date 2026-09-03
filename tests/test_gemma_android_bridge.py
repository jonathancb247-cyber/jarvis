import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from jarvis_core.ai.contracts import (
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
)
from jarvis_core.ai.gemma_android_bridge import (
    GEMMA_ANDROID_BRIDGE_GENERATE_PATH,
    GemmaAndroidBridgeConfig,
    GemmaAndroidBridgeTransport,
)
from jarvis_core.ai.gemma_local import (
    GemmaLocalAIProvider,
    GemmaLocalProviderConfig,
    GemmaLocalProviderError,
)
from tests.test_gemma_local_provider import safe_context, success_plan


class GemmaAndroidBridgeConfigTests(unittest.TestCase):
    def test_config_requires_explicit_bounded_host_and_port(self):
        config = GemmaAndroidBridgeConfig("192.168.1.44", port=8767)

        self.assertEqual(config.host, "192.168.1.44")
        self.assertEqual(config.port, 8767)
        for host in ("", "http://192.168.1.44", "192.168.1.44/generate", "bad host"):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    GemmaAndroidBridgeConfig(host)
        with self.assertRaises(ValueError):
            GemmaAndroidBridgeConfig("192.168.1.44", port=0)

    def test_localhost_and_loopback_are_allowed(self):
        for host in ("localhost", "127.0.0.1", "::1"):
            with self.subTest(host=host):
                config = GemmaAndroidBridgeConfig(host)
                self.assertEqual(config.host, host)

    def test_private_ipv4_addresses_are_allowed(self):
        for host in (
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.255.255",
            "169.254.0.1",
        ):
            with self.subTest(host=host):
                config = GemmaAndroidBridgeConfig(host)
                self.assertEqual(config.host, host)

    def test_public_ipv4_addresses_are_rejected(self):
        for host in ("8.8.8.8", "1.1.1.1", "9.9.9.9", "104.16.0.1"):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    GemmaAndroidBridgeConfig(host)

    def test_public_hostnames_are_rejected(self):
        for host in ("example.com", "google.com", "api.openai.com"):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    GemmaAndroidBridgeConfig(host)


class GemmaAndroidBridgeTransportTests(unittest.TestCase):
    def test_transport_posts_provider_request_to_fixed_generate_path(self):
        plan = success_plan()
        connection = FakeConnection(
            FakeHttpResponse(
                200,
                json.dumps({"plan": plan}).encode("utf-8"),
            )
        )
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=_transport_with_connection(connection),
        )

        payload = provider.generate_plan(safe_context("Read status.read from lamp_1."))
        sent = connection.requests[0]

        self.assertEqual(payload["kind"], "execute")
        self.assertEqual(connection.host, "192.168.1.44")
        self.assertEqual(connection.port, 8767)
        self.assertEqual(connection.timeout, 60)
        self.assertEqual(sent["method"], "POST")
        self.assertEqual(sent["path"], GEMMA_ANDROID_BRIDGE_GENERATE_PATH)
        self.assertEqual(sent["headers"]["Content-Type"], "application/json")
        self.assertEqual(sent["headers"]["Accept"], "application/json")
        request = json.loads(sent["body"].decode("utf-8"))
        self.assertEqual(request["provider"], "gemma-local")
        self.assertEqual(request["model"], "gemma-4-e2b")
        self.assertFalse(request["execution"]["runtime"])
        self.assertFalse(request["execution"]["drivers"])
        self.assertFalse(request["execution"]["tools"])

    def test_valid_text_json_response_envelope_passes_through_to_provider(self):
        plan = success_plan()
        connection = FakeConnection(
            FakeHttpResponse(
                200,
                json.dumps({"output_text": json.dumps(plan)}).encode("utf-8"),
            )
        )
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("gemma-4-e2b"),
            transport=_transport_with_connection(connection),
        )

        payload = provider.generate_plan(safe_context("Read status.read from lamp_1."))

        self.assertEqual(payload["canonical_command_text"] if "canonical_command_text" in payload else payload["steps"][0]["canonical_command_text"], "device read lamp_1 status.read")

    def test_valid_tool_call_response_envelope_passes_through_to_provider(self):
        plan = success_plan()
        connection = FakeConnection(
            FakeHttpResponse(
                200,
                json.dumps(
                    {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "ai_action_plan",
                                    "arguments": plan,
                                }
                            }
                        ]
                    }
                ).encode("utf-8"),
            )
        )
        provider = GemmaLocalAIProvider(
            GemmaLocalProviderConfig("function-gemma-270m"),
            transport=_transport_with_connection(connection),
        )

        payload = provider.generate_plan(safe_context("Read status.read from lamp_1."))

        self.assertEqual(payload["kind"], "execute")
        self.assertEqual(payload["steps"][0]["canonical_command_text"], "device read lamp_1 status.read")

    def test_status_errors_are_normalized(self):
        cases = [
            (302, AI_PROVIDER_PROTOCOL_ERROR),
            (400, AI_PROVIDER_PROTOCOL_ERROR),
            (408, AI_PROVIDER_TIMEOUT),
            (413, AI_RESPONSE_TOO_LARGE),
            (500, AI_PROVIDER_UNAVAILABLE),
        ]
        for status, code in cases:
            with self.subTest(status=status):
                connection = FakeConnection(
                    FakeHttpResponse(status, b'{"error":"hidden"}')
                )
                transport = _transport_with_connection(connection)

                with self.assertRaises(GemmaLocalProviderError) as raised:
                    transport.generate({"hello": "world"}, 10, 1024)

                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("hidden", str(raised.exception))
                self.assertEqual(len(connection.requests), 1)
                self.assertEqual(connection.response.read_calls, 0)

    def test_timeout_and_connection_errors_are_normalized(self):
        cases = [
            (TimeoutError("raw timeout"), AI_PROVIDER_TIMEOUT),
            (OSError("raw socket"), AI_PROVIDER_UNAVAILABLE),
        ]
        for error, code in cases:
            with self.subTest(error=error):
                transport = _transport_with_connection(FakeConnection(raise_error=error))

                with self.assertRaises(GemmaLocalProviderError) as raised:
                    transport.generate({"hello": "world"}, 10, 1024)

                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("raw", str(raised.exception))

    def test_oversized_malformed_empty_and_non_json_responses_are_normalized(self):
        cases = [
            (FakeHttpResponse(200, b""), AI_RESPONSE_INVALID),
            (FakeHttpResponse(200, b"not json"), AI_RESPONSE_INVALID),
            (FakeHttpResponse(200, b"[]"), AI_RESPONSE_INVALID),
            (
                FakeHttpResponse(200, b'{"plan":{}}', headers=(("Content-Type", "text/plain"),)),
                AI_PROVIDER_PROTOCOL_ERROR,
            ),
            (FakeHttpResponse(200, b'{"x":"' + (b"a" * 1024) + b'"}'), AI_RESPONSE_TOO_LARGE),
        ]
        for response, code in cases:
            with self.subTest(code=code):
                transport = _transport_with_connection(FakeConnection(response))

                with self.assertRaises(GemmaLocalProviderError) as raised:
                    transport.generate({"hello": "world"}, 10, 1024)

                self.assertEqual(raised.exception.code, code)

    def test_content_length_oversized_is_rejected_before_read(self):
        response = FakeHttpResponse(
            200,
            b'{"plan":{}}',
            headers=(
                ("Content-Type", "application/json"),
                ("Content-Length", "2048"),
            ),
        )
        transport = _transport_with_connection(FakeConnection(response))

        with self.assertRaises(GemmaLocalProviderError) as raised:
            transport.generate({"hello": "world"}, 10, 1024)

        self.assertEqual(raised.exception.code, AI_RESPONSE_TOO_LARGE)
        self.assertEqual(response.read_calls, 0)

    def test_invalid_content_length_is_protocol_error(self):
        cases = [
            (("Content-Length", "not-a-number"),),
            (("Content-Length", "-1"),),
            (("Content-Length", "1"), ("Content-Length", "1")),
        ]
        for extra_headers in cases:
            with self.subTest(extra_headers=extra_headers):
                response = FakeHttpResponse(
                    200,
                    b'{"plan":{}}',
                    headers=(("Content-Type", "application/json"),) + extra_headers,
                )
                transport = _transport_with_connection(FakeConnection(response))

                with self.assertRaises(GemmaLocalProviderError) as raised:
                    transport.generate({"hello": "world"}, 10, 1024)

                self.assertEqual(raised.exception.code, AI_PROVIDER_PROTOCOL_ERROR)
                self.assertEqual(response.read_calls, 0)

    def test_no_content_length_oversized_response_still_uses_bounded_read(self):
        response = FakeHttpResponse(200, b'{"x":"' + (b"a" * 1024) + b'"}')
        transport = _transport_with_connection(FakeConnection(response))

        with self.assertRaises(GemmaLocalProviderError) as raised:
            transport.generate({"hello": "world"}, 10, 1024)

        self.assertEqual(raised.exception.code, AI_RESPONSE_TOO_LARGE)
        self.assertEqual(response.read_amounts, [1025])

    def test_invalid_timeout_and_response_limit_are_rejected_before_network(self):
        connection = FakeConnection(FakeHttpResponse(200, b'{"plan":{}}'))
        transport = _transport_with_connection(connection)

        with self.assertRaises(ValueError):
            transport.generate({"hello": "world"}, 0, 1024)
        with self.assertRaises(ValueError):
            transport.generate({"hello": "world"}, 10, 10)
        self.assertEqual(connection.requests, [])

    def test_non_serializable_request_is_protocol_error(self):
        transport = _transport_with_connection(FakeConnection(FakeHttpResponse(200, b"{}")))

        with self.assertRaises(GemmaLocalProviderError) as raised:
            transport.generate({"bad": object()}, 10, 1024)

        self.assertEqual(raised.exception.code, AI_PROVIDER_PROTOCOL_ERROR)

    def test_bridge_module_does_not_import_execution_voice_or_stt_boundaries(self):
        source = Path("jarvis_core/ai/gemma_android_bridge.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

        forbidden = (
            "jarvis_core.runtime",
            "jarvis_core.drivers",
            "jarvis_core.device_state",
            "jarvis_core.api",
            "jarvis_core.dashboard",
            "jarvis_core.voice",
            "jarvis_core.planner",
        )
        self.assertFalse(
            any(module.startswith(forbidden) for module in imported_modules),
            imported_modules,
        )


def _transport_with_connection(connection):
    config = GemmaAndroidBridgeConfig("192.168.1.44", port=8767)
    transport = GemmaAndroidBridgeTransport(config)

    def connection_factory(host, port, timeout):
        connection.host = host
        connection.port = port
        connection.timeout = timeout
        return connection

    class TransportWithPatchedConnection(GemmaAndroidBridgeTransport):
        def generate(self, request, timeout_seconds, max_response_bytes):
            with patch("http.client.HTTPConnection", connection_factory):
                return super().generate(request, timeout_seconds, max_response_bytes)

    return TransportWithPatchedConnection(config)


class FakeConnection:
    def __init__(self, response=None, *, raise_error=None):
        self.response = response
        self.raise_error = raise_error
        self.requests = []
        self.closed = False
        self.host = None
        self.port = None
        self.timeout = None

    def request(self, method, path, body=None, headers=None):
        if self.raise_error is not None:
            raise self.raise_error
        self.requests.append(
            {
                "method": method,
                "path": path,
                "body": body,
                "headers": dict(headers or {}),
            }
        )

    def getresponse(self):
        if self.raise_error is not None:
            raise self.raise_error
        return self.response

    def close(self):
        self.closed = True


class FakeHttpResponse:
    def __init__(
        self,
        status,
        body,
        *,
        headers=(("Content-Type", "application/json; charset=utf-8"),),
    ):
        self.status = status
        self.body = body
        self.headers = headers
        self.read_calls = 0
        self.read_amounts = []

    def read(self, amount):
        self.read_calls += 1
        self.read_amounts.append(amount)
        return self.body[:amount]

    def getheaders(self):
        return self.headers


if __name__ == "__main__":
    unittest.main()
