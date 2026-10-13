"""Tests for the authenticated, non-executing local interaction endpoint.

These tests prove the API interaction increment invariants:

- ``POST /api/v1/interactions`` is mounted only in explicit interaction-only
  mode and requires a constant-time Bearer token; it fails closed without one;
- the endpoint reuses the existing ``handle_interaction`` boundary, builds its
  context server-side and never calls Runtime, Drivers or the ExecutionGate;
- provider outcome categories are preserved as explicit HTTP statuses
  (503 unavailable, 504 timeout, 502 invalid) instead of being rewritten into
  successful conversations;
- unsafe framing, payloads and over-long messages are rejected before any
  provider call;
- ``commands_executed`` is always false and canonical command text is never
  exposed.
"""

import json
import socket
import threading
import time
import unittest

from jarvis_core.ai.contracts import (
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
)
from jarvis_core.ai.gemma_local import GemmaLocalResponse
from jarvis_core.ai.gemma_understanding import (
    GemmaLocalUnderstandingProvider,
    GemmaUnderstandingProviderConfig,
)
from jarvis_core.ai.interaction import INTERACTION_TYPE_CONVERSATION
from jarvis_core.ai.interaction import INTERACTION_TYPE_UNDERSTANDING
from jarvis_core.ai.understanding_decision import (
    EXECUTABLE_CANDIDATE,
    LOCAL_AI_UNAVAILABLE,
    NEEDS_CLARIFICATION,
    REFUSED,
    UNDERSTANDING_FAILED,
)
from jarvis_core.api import errors
from jarvis_core.api.adapter import RuntimeApiAdapter
from jarvis_core.api.interaction_service import (
    MIN_INTERACTION_TOKEN_LENGTH,
    InteractionAuth,
    LocalInteractionService,
)
from jarvis_core.api.projections import ApiProjectionBuilder
from jarvis_core.api.server import _parse_content_length, make_server
from jarvis_core.api.validation import (
    MAX_INTERACTION_MESSAGE_LENGTH,
    MAX_REQUEST_BYTES,
)
from jarvis_core.devices import (
    Device,
    DeviceCapability,
    DeviceRegistry,
    DeviceState,
)

TOKEN = "test-interaction-token"
READ_MESSAGE = "Lee status.read del dispositivo lamp_1."
MUTATE_MESSAGE = "Enciende power.switch del dispositivo lamp_1 con state true."


class RecordingRuntime:
    """Runtime spy that records every adapter input and never executes."""

    def __init__(self):
        self.calls = []

    def handle_adapter_input(self, text, source="cli"):
        self.calls.append((text, source))
        raise AssertionError("the interaction endpoint must never call Runtime")

    def shutdown(self):
        self.calls.append(("shutdown", "runtime"))


class SpyUnderstandingProvider:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def extract_understanding(self, context):
        self.calls.append(context.user_request)
        if self.error is not None:
            raise self.error
        return self.output


class BlockingProvider:
    """Provider that blocks inside ``extract_understanding`` until released."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def extract_understanding(self, context):
        self.entered.set()
        self.release.wait(timeout=5)
        return read_proposal()


class StubGemmaUnderstandingTransport:
    def __init__(self, body=None, *, error=None):
        self.body = body
        self.error = error
        self.requests = []

    def generate(self, request, timeout_seconds, max_response_bytes):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return GemmaLocalResponse(self.body)


def read_proposal():
    return {
        "intent": "read",
        "referenced_device_id": "lamp_1",
        "capability_hint": "status.read",
        "operation_hint": "read",
    }


def mutate_proposal():
    return {
        "intent": "mutate",
        "referenced_device_id": "lamp_1",
        "capability_hint": "power.switch",
        "operation_hint": "apply",
        "raw_arguments": [["state", "true"]],
    }


def ambiguous_proposal():
    return {
        "intent": "mutate",
        "referenced_device_text": "light",
        "capability_hint": "power.switch",
        "operation_hint": "apply",
        "raw_arguments": [["state", "true"]],
    }


def build_registry(*, include_second_lamp=False):
    registry = DeviceRegistry()
    registry.register(device("lamp_1", "Lamp"))
    if include_second_lamp:
        registry.register(device("lamp_2", "Desk Lamp"))
    return registry


def device(device_id, name):
    return Device(
        id=device_id,
        name=name,
        type="light",
        capabilities=[
            DeviceCapability(name="status.read", kind="reading"),
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"type": "string", "required": True}},
            ),
        ],
        state=DeviceState(status="known", properties={"power": False}),
    )


def build_service(provider, *, max_concurrency=2, registry=None):
    return LocalInteractionService(
        registry or build_registry(),
        provider,
        provider_id="spy-understanding",
        model_id="spy-test",
        max_concurrency=max_concurrency,
    )


def build_adapter(provider, *, token=TOKEN, interaction_only=True, registry=None):
    registry = registry or build_registry()
    runtime = RecordingRuntime()
    adapter = RuntimeApiAdapter(
        runtime,
        ApiProjectionBuilder(registry),
        interaction_service=build_service(provider, registry=registry),
        interaction_auth=InteractionAuth(token),
        interaction_only=interaction_only,
    )
    return adapter, runtime


def post(adapter, message, *, token=TOKEN, content_type="application/json"):
    headers = {"Content-Type": content_type}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return adapter.handle_request(
        "POST",
        "/api/v1/interactions",
        headers,
        json.dumps({"message": message}).encode("utf-8"),
    )


class InteractionAuthTests(unittest.TestCase):
    def test_valid_bearer_token_authorizes(self):
        auth = InteractionAuth(TOKEN)
        self.assertIsNone(auth.authorize(f"Bearer {TOKEN}"))
        self.assertIsNone(auth.authorize(f"bearer {TOKEN}"))

    def test_missing_or_mismatched_token_is_unauthorized(self):
        auth = InteractionAuth(TOKEN)
        for header in (None, "", "Bearer", "Bearer wrong", "Basic abc", TOKEN):
            with self.subTest(header=header):
                with self.assertRaises(errors.ApiError) as raised:
                    auth.authorize(header)
                self.assertEqual(raised.exception.code, errors.API_UNAUTHORIZED)
                self.assertEqual(raised.exception.status, 401)

    def test_unconfigured_token_fails_closed(self):
        for token in ("", "   ", "a\nb", "a\rb", None):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    InteractionAuth(token)

    def test_token_configuration_is_strict(self):
        invalid = (
            "short",  # below minimum length
            "a" * (MIN_INTERACTION_TOKEN_LENGTH - 1),
            "with spaces token",  # embedded whitespace
            "token\twith\ttabs-length",  # control whitespace
            "tökén-tökén-tökén",  # non-ASCII
            "token\nnewline-long-enough",  # newline
        )
        for token in invalid:
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    InteractionAuth(token)

    def test_minimum_length_printable_token_is_accepted(self):
        token = "a" * MIN_INTERACTION_TOKEN_LENGTH
        auth = InteractionAuth(token)
        self.assertIsNone(auth.authorize(f"Bearer {token}"))

    def test_non_ascii_authorization_header_is_unauthorized_not_error(self):
        auth = InteractionAuth(TOKEN)
        headers = ("Bearer tökén", "Béarer " + TOKEN, "é", "\u00e9" + TOKEN)
        for header in headers:
            with self.subTest(header=header):
                with self.assertRaises(errors.ApiError) as raised:
                    auth.authorize(header)
                self.assertEqual(raised.exception.code, errors.API_UNAUTHORIZED)
                self.assertEqual(raised.exception.status, 401)


class InteractionEndpointAuthTests(unittest.TestCase):
    def test_missing_token_is_rejected_before_provider_call(self):
        provider = SpyUnderstandingProvider(read_proposal())
        adapter, runtime = build_adapter(provider)

        response = post(adapter, READ_MESSAGE, token=None)

        self.assertEqual(response.status, 401)
        self.assertFalse(response.body["success"])
        self.assertEqual(response.body["error"], "api_unauthorized")
        self.assertEqual(provider.calls, [])
        self.assertEqual(runtime.calls, [])

    def test_wrong_token_is_rejected(self):
        provider = SpyUnderstandingProvider(read_proposal())
        adapter, _ = build_adapter(provider)

        response = post(adapter, READ_MESSAGE, token="not-the-token")

        self.assertEqual(response.status, 401)
        self.assertEqual(provider.calls, [])

    def test_endpoint_is_not_mounted_without_interaction_service(self):
        adapter = RuntimeApiAdapter(RecordingRuntime(), ApiProjectionBuilder(build_registry()))

        response = adapter.handle_request(
            "POST",
            "/api/v1/interactions",
            {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
            json.dumps({"message": "hola"}).encode("utf-8"),
        )

        self.assertEqual(response.status, 404)
        self.assertEqual(response.body["error"], "api_route_not_found")


class InteractionEndpointBehaviorTests(unittest.TestCase):
    def test_pure_greeting_returns_conversation_without_provider(self):
        provider = SpyUnderstandingProvider(error=RuntimeError("must not be called"))
        adapter, runtime = build_adapter(provider)

        response = post(adapter, "hola")

        self.assertEqual(response.status, 200)
        self.assertTrue(response.body["success"])
        self.assertIsNone(response.body["error"])
        self.assertEqual(response.body["type"], INTERACTION_TYPE_CONVERSATION)
        self.assertIsNone(response.body["decision"])
        self.assertIs(response.body["commands_executed"], False)
        self.assertEqual(provider.calls, [])
        self.assertEqual(runtime.calls, [])

    def test_read_request_is_validated_candidate_and_not_executed(self):
        provider = SpyUnderstandingProvider(read_proposal())
        adapter, runtime = build_adapter(provider)

        response = post(adapter, READ_MESSAGE)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["type"], INTERACTION_TYPE_UNDERSTANDING)
        self.assertEqual(
            response.body["decision"]["status"], EXECUTABLE_CANDIDATE
        )
        self.assertIs(response.body["commands_executed"], False)
        self.assertIs(response.body["decision"]["commands_executed"], False)
        self.assertNotIn("canonical_command_text", response.body["decision"])
        self.assertEqual(provider.calls, [READ_MESSAGE])
        self.assertEqual(runtime.calls, [])

    def test_mutation_is_confirmation_candidate_not_executed(self):
        provider = SpyUnderstandingProvider(mutate_proposal())
        adapter, runtime = build_adapter(provider)

        response = post(adapter, MUTATE_MESSAGE)

        self.assertEqual(response.status, 200)
        self.assertEqual(
            response.body["decision"]["status"], EXECUTABLE_CANDIDATE
        )
        self.assertTrue(response.body["decision"]["confirmation_required"])
        self.assertIs(response.body["commands_executed"], False)
        self.assertEqual(runtime.calls, [])

    def test_ambiguous_request_preserves_clarification(self):
        provider = SpyUnderstandingProvider(ambiguous_proposal())
        adapter, _ = build_adapter(
            provider, registry=build_registry(include_second_lamp=True)
        )

        response = post(adapter, "Enciende la luz.")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["decision"]["status"], NEEDS_CLARIFICATION)

    def test_destructive_request_is_refused_not_answered(self):
        provider = SpyUnderstandingProvider(read_proposal())
        adapter, _ = build_adapter(provider)

        response = post(adapter, "Borra todos los dispositivos.")

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["decision"]["status"], REFUSED)
        self.assertIs(response.body["commands_executed"], False)

    def test_provider_unavailable_maps_to_503(self):
        provider = provider_with(transport_error=OSError("connection refused"))
        adapter, runtime = build_adapter(provider)

        response = post(adapter, READ_MESSAGE)

        self.assertEqual(response.status, 503)
        self.assertFalse(response.body["success"])
        self.assertEqual(
            response.body["error"], "api_interaction_provider_unavailable"
        )
        self.assertEqual(
            response.body["decision"]["status"], LOCAL_AI_UNAVAILABLE
        )
        self.assertEqual(
            response.body["decision"]["failure_category"], AI_PROVIDER_UNAVAILABLE
        )
        self.assertIs(response.body["commands_executed"], False)
        self.assertEqual(runtime.calls, [])

    def test_provider_timeout_maps_to_504(self):
        provider = provider_with(transport_error=TimeoutError())
        adapter, _ = build_adapter(provider)

        response = post(adapter, READ_MESSAGE)

        self.assertEqual(response.status, 504)
        self.assertEqual(response.body["error"], "api_interaction_provider_timeout")
        self.assertEqual(
            response.body["decision"]["status"], UNDERSTANDING_FAILED
        )
        self.assertEqual(
            response.body["decision"]["failure_category"], AI_PROVIDER_TIMEOUT
        )
        self.assertIs(response.body["commands_executed"], False)

    def test_invalid_provider_response_maps_to_502(self):
        provider = SpyUnderstandingProvider({"kind": "execute", "steps": []})
        adapter, _ = build_adapter(provider)

        response = post(adapter, READ_MESSAGE)

        self.assertEqual(response.status, 502)
        self.assertEqual(response.body["error"], "api_interaction_provider_invalid")
        self.assertEqual(
            response.body["decision"]["status"], UNDERSTANDING_FAILED
        )
        self.assertEqual(
            response.body["decision"]["failure_category"], AI_RESPONSE_INVALID
        )

    def test_malformed_transport_body_maps_to_502(self):
        provider = provider_with(body="not json")
        adapter, _ = build_adapter(provider)

        response = post(adapter, READ_MESSAGE)

        self.assertEqual(response.status, 502)
        self.assertEqual(response.body["error"], "api_interaction_provider_invalid")


class InteractionEndpointValidationTests(unittest.TestCase):
    def setUp(self):
        self.adapter, self.runtime = build_adapter(
            SpyUnderstandingProvider(read_proposal())
        )

    def _raw(self, body, *, headers=None):
        return self.adapter.handle_request(
            "POST",
            "/api/v1/interactions",
            headers
            or {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {TOKEN}",
            },
            body,
        )

    def test_invalid_payloads_are_rejected(self):
        cases = [
            b"{}",
            b'{"message": ""}',
            b'{"message": "   "}',
            b'{"message": 5}',
            b'{"message": "hola", "extra": true}',
            b'{"message": "hola", "message": "hola"}',
            b'{"message": " hola"}',
            b'{"message": "hola\\n"}',
            b"{",
            b"\xff",
            json.dumps(
                {"message": "x" * (MAX_INTERACTION_MESSAGE_LENGTH + 1)}
            ).encode("utf-8"),
        ]
        for body in cases:
            with self.subTest(body=body):
                response = self._raw(body)
                self.assertEqual(response.status, 400)

    def test_wrong_content_type_is_rejected(self):
        response = self._raw(
            b'{"message": "hola"}',
            headers={
                "Content-Type": "text/plain",
                "Authorization": f"Bearer {TOKEN}",
            },
        )
        self.assertEqual(response.status, 415)

    def test_maximum_length_message_passes_validation(self):
        message = "a" * MAX_INTERACTION_MESSAGE_LENGTH
        response = self._raw(json.dumps({"message": message}).encode("utf-8"))
        self.assertNotEqual(response.status, 400)


class InteractionOnlyModeTests(unittest.TestCase):
    def test_commands_are_disabled_in_interaction_only_mode(self):
        adapter, runtime = build_adapter(SpyUnderstandingProvider(read_proposal()))

        response = adapter.handle_request(
            "POST",
            "/api/v1/commands",
            {"Content-Type": "application/json"},
            json.dumps({"input": "device list"}).encode("utf-8"),
        )

        self.assertEqual(response.status, 404)
        self.assertEqual(response.body["error"], "api_route_not_found")
        self.assertEqual(runtime.calls, [])

    def test_read_only_projections_remain_available(self):
        adapter, _ = build_adapter(SpyUnderstandingProvider(read_proposal()))

        health = adapter.handle_request("GET", "/api/v1/health")
        devices = adapter.handle_request("GET", "/api/v1/devices")

        self.assertEqual(health.status, 200)
        self.assertEqual(health.body["status"], "ok")
        self.assertEqual(devices.status, 200)
        self.assertEqual(devices.body["devices"][0]["device_id"], "lamp_1")

    def test_commands_remain_available_in_default_mode(self):
        class OkRuntime(RecordingRuntime):
            def handle_adapter_input(self, text, source="cli"):
                self.calls.append((text, source))
                from jarvis_core.domain import CapabilityResult

                return CapabilityResult(True, "ok", {}, None)

        ok_runtime = OkRuntime()
        adapter = RuntimeApiAdapter(ok_runtime, ApiProjectionBuilder(build_registry()))
        response = adapter.handle_request(
            "POST",
            "/api/v1/commands",
            {"Content-Type": "application/json"},
            json.dumps({"input": "device list"}).encode("utf-8"),
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(ok_runtime.calls, [("device list", "api")])


class InteractionConcurrencyTests(unittest.TestCase):
    def test_bounded_concurrency_fails_fast_when_busy(self):
        provider = BlockingProvider()
        service = build_service(provider, max_concurrency=1)
        outcomes = []

        def first_turn():
            outcomes.append(service.handle(READ_MESSAGE))

        worker = threading.Thread(target=first_turn)
        worker.start()
        self.assertTrue(provider.entered.wait(timeout=5))
        try:
            with self.assertRaises(errors.ApiError) as raised:
                service.handle(READ_MESSAGE)
            self.assertEqual(raised.exception.code, errors.API_INTERACTION_BUSY)
            self.assertEqual(raised.exception.status, 503)
        finally:
            provider.release.set()
            worker.join(timeout=5)

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].status, 200)


class InteractionServiceConstructionTests(unittest.TestCase):
    def test_provider_must_expose_extract_understanding(self):
        with self.assertRaises(TypeError):
            LocalInteractionService(
                build_registry(),
                object(),
                provider_id="spy",
                model_id="spy-test",
            )

    def test_max_concurrency_must_be_positive(self):
        with self.assertRaises(ValueError):
            build_service(SpyUnderstandingProvider(read_proposal()), max_concurrency=0)

    def test_service_rejects_context_that_cannot_preserve_message(self):
        service = build_service(SpyUnderstandingProvider(read_proposal()))
        with self.assertRaises(errors.ApiError) as raised:
            service.handle("  padded  ")
        self.assertEqual(raised.exception.status, 400)


class InteractionServerFramingTests(unittest.TestCase):
    def setUp(self):
        self.adapter, _ = build_adapter(SpyUnderstandingProvider(read_proposal()))
        self.server = make_server(self.adapter, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _raw_status(self, request_bytes):
        status = self._raw_status_or_none(request_bytes)
        self.assertIsNotNone(status, "server returned no HTTP response")
        return status

    def _raw_status_or_none(self, request_bytes):
        host, port = self.server.server_address
        with socket.create_connection((host, port), timeout=5) as connection:
            connection.sendall(request_bytes)
            connection.settimeout(5)
            try:
                data = connection.recv(2048)
            except socket.timeout:
                return None
        if not data:
            return None
        return int(data.split(b" ", 2)[1])

    def test_transfer_encoding_is_rejected(self):
        status = self._raw_status(
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Authorization: Bearer " + TOKEN.encode("utf-8") + b"\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
        )
        self.assertEqual(status, 400)

    def test_duplicate_content_length_is_rejected(self):
        status = self._raw_status(
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Authorization: Bearer " + TOKEN.encode("utf-8") + b"\r\n"
            b"Content-Length: 5\r\n"
            b"Content-Length: 7\r\n\r\nhello!!"
        )
        self.assertEqual(status, 400)

    def test_non_digit_content_length_is_rejected(self):
        for value in (b"+19", b"1_9", b"0x13", b"-19", b"19.0"):
            with self.subTest(value=value):
                status = self._raw_status(
                    b"POST /api/v1/interactions HTTP/1.1\r\n"
                    b"Host: 127.0.0.1\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Authorization: Bearer " + TOKEN.encode("utf-8") + b"\r\n"
                    b"Content-Length: " + value + b"\r\n\r\n"
                )
                self.assertEqual(status, 400)

    def test_oversized_content_length_is_rejected_without_reading_body(self):
        status = self._raw_status(
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Authorization: Bearer " + TOKEN.encode("utf-8") + b"\r\n"
            b"Content-Length: "
            + str(MAX_REQUEST_BYTES + 1).encode("ascii")
            + b"\r\n\r\n"
        )
        self.assertEqual(status, 413)

    def test_valid_framed_request_is_dispatched(self):
        body = json.dumps({"message": "hola"}).encode("utf-8")
        status = self._raw_status(
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Authorization: Bearer " + TOKEN.encode("utf-8") + b"\r\n"
            b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        )
        self.assertEqual(status, 200)

    def test_body_is_read_exactly_to_declared_length(self):
        # The body is longer than Content-Length, so exactly five bytes are read.
        # The truncated prefix is invalid JSON, proving no over-read occurred.
        status = self._raw_status(
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Authorization: Bearer " + TOKEN.encode("utf-8") + b"\r\n"
            b"Content-Length: 5\r\n\r\n"
            b'{"message": "hola"}'
        )
        self.assertEqual(status, 400)

    def test_non_ascii_authorization_header_is_rejected_before_body_read(self):
        status = self._raw_status(
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Authorization: Bearer t\xf8ken\r\n"
            b"Content-Length: 1000\r\n\r\n"
        )
        self.assertEqual(status, 401)

    def test_invalid_token_is_rejected_before_body_is_read(self):
        # No body is sent despite a declared Content-Length. A prompt 401 proves
        # the server authenticated before attempting to read the interaction body.
        status = self._raw_status(
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Authorization: Bearer wrong-token\r\n"
            b"Content-Length: 1000\r\n\r\n"
        )
        self.assertEqual(status, 401)

    def _interaction_head(self, content_length_bytes):
        return (
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            b"Authorization: Bearer " + TOKEN.encode("utf-8") + b"\r\n"
            b"Content-Length: " + content_length_bytes + b"\r\n\r\n"
        )

    def test_five_thousand_digit_content_length_is_rejected(self):
        # A huge all-digit length must be refused with a bounded HTTP response,
        # not crash on int() conversion.
        status = self._raw_status_or_none(self._interaction_head(b"9" * 5000))
        self.assertEqual(status, 413)

    def test_thousands_of_zeros_content_length_is_bounded(self):
        # A long run of leading zeros is a valid representation of zero and must
        # not raise; with no body the interaction payload is rejected as invalid.
        status = self._raw_status_or_none(self._interaction_head(b"0" * 5000))
        self.assertEqual(status, 400)

    def test_valid_request_succeeds_after_malformed_content_lengths(self):
        for value in (b"9" * 5000, b"0" * 5000, b"+19", b"1_9"):
            with self.subTest(prefix=value[:8]):
                self._raw_status_or_none(self._interaction_head(value))
        body = json.dumps({"message": "hola"}).encode("utf-8")
        status = self._raw_status_or_none(
            self._interaction_head(str(len(body)).encode("ascii")) + body
        )
        self.assertEqual(status, 200)


class ContentLengthParsingTests(unittest.TestCase):
    def test_ascii_digits_only(self):
        for value in ("18", "0", "000123"):
            with self.subTest(value=value):
                self.assertEqual(_parse_content_length(value), int(value))

    def test_non_ascii_or_non_digit_is_rejected(self):
        values = (
            "+18",
            "1_8",
            " 18",
            "18 ",
            "0x13",
            "-18",
            "18.0",
            "1,8",
            "\u0661\u0668",  # non-ASCII digits
            "",
            "abc",
        )
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(errors.ApiError) as raised:
                    _parse_content_length(value)
                self.assertEqual(raised.exception.status, 400)

    def test_non_string_is_rejected(self):
        with self.assertRaises(errors.ApiError):
            _parse_content_length(None)

    def test_thousands_of_digits_is_rejected_without_conversion_error(self):
        with self.assertRaises(errors.ApiError) as raised:
            _parse_content_length("9" * 5000)
        self.assertEqual(raised.exception.status, 413)

    def test_thousands_of_zeros_is_bounded(self):
        self.assertEqual(_parse_content_length("0" * 5000), 0)

    def test_long_zero_prefix_small_value_is_accepted(self):
        self.assertEqual(_parse_content_length("0" * 4999 + "18"), 18)


class _FakeRequestSocket:
    """Minimal socket stand-in for admission-rejection tests."""

    def __init__(self):
        self.sent = []
        self.closed = False
        self.timeout = None

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


class InteractionServerAdmissionTests(unittest.TestCase):
    def test_over_capacity_connection_is_rejected_and_closed(self):
        adapter, _ = build_adapter(SpyUnderstandingProvider(read_proposal()))
        server = make_server(adapter, port=0, max_connections=1)
        try:
            self.assertTrue(server._admission.acquire(blocking=False))
            request = _FakeRequestSocket()
            server.process_request(request, ("127.0.0.1", 0))
            self.assertTrue(request.sent)
            self.assertTrue(request.sent[0].startswith(b"HTTP/1.1 503"))
            self.assertIn(b"api_server_busy", request.sent[0])
            self.assertTrue(request.closed)
        finally:
            server.server_close()

    def test_max_connections_must_be_positive(self):
        adapter, _ = build_adapter(SpyUnderstandingProvider(read_proposal()))
        with self.assertRaises(ValueError):
            make_server(adapter, port=0, max_connections=0)


class InteractionServerDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.adapter, _ = build_adapter(SpyUnderstandingProvider(read_proposal()))
        self.server = make_server(self.adapter, port=0)
        self.server.request_total_budget_seconds = 0.5
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_slow_body_is_bounded_by_total_deadline(self):
        host, port = self.server.server_address
        started = time.monotonic()
        with socket.create_connection((host, port), timeout=5) as connection:
            connection.sendall(
                b"POST /api/v1/interactions HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Authorization: Bearer " + TOKEN.encode("utf-8") + b"\r\n"
                b"Content-Length: 1000\r\n\r\n"
                b"{"
            )
            connection.settimeout(5)
            data = connection.recv(2048)
        self.assertLess(time.monotonic() - started, 4)
        if data:
            self.assertEqual(data.split(b" ", 2)[1], b"400")

    def test_slow_header_is_bounded_by_total_deadline(self):
        host, port = self.server.server_address
        started = time.monotonic()
        with socket.create_connection((host, port), timeout=5) as connection:
            connection.sendall(
                b"POST /api/v1/interactions HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
            )
            connection.settimeout(5)
            data = connection.recv(2048)
        self.assertLess(time.monotonic() - started, 4)
        self.assertTrue(data == b"" or data.startswith(b"HTTP/1.1"))


class InteractionServerSlowlorisTests(unittest.TestCase):
    MAX_CONNECTIONS = 2
    BUDGET_SECONDS = 0.3

    def setUp(self):
        self.adapter, _ = build_adapter(SpyUnderstandingProvider(read_proposal()))
        self.server = make_server(
            self.adapter, port=0, max_connections=self.MAX_CONNECTIONS
        )
        self.server.request_total_budget_seconds = self.BUDGET_SECONDS
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.02)
        )
        self.thread.daemon = True
        self.thread.start()
        self._stop = threading.Event()
        self._connections = []
        self._workers = []

    def tearDown(self):
        self._stop.set()
        for worker in self._workers:
            worker.join(timeout=2)
        for connection in self._connections:
            try:
                connection.close()
            except OSError:
                pass
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _start_drip(self, prefix):
        host, port = self.server.server_address
        connection = socket.create_connection((host, port), timeout=5)
        self._connections.append(connection)
        connection.sendall(prefix)

        def drip():
            try:
                while not self._stop.is_set():
                    connection.sendall(b"X")
                    time.sleep(0.06)
            except OSError:
                pass

        worker = threading.Thread(target=drip)
        worker.daemon = True
        worker.start()
        self._workers.append(worker)

    def _wait_until(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.01)
        return predicate()

    def _occupied(self):
        return self.server._admission._value == 0

    def _released(self):
        return self.server._admission._value == self.MAX_CONNECTIONS

    def test_periodic_request_line_drip_releases_all_slots(self):
        for _ in range(self.MAX_CONNECTIONS):
            self._start_drip(b"POST /api/v1/interactions HTTP/1.1")
        self.assertTrue(self._wait_until(self._occupied, 2), "slots never saturated")
        release_started = time.monotonic()
        released = self._wait_until(self._released, 2)
        elapsed = time.monotonic() - release_started
        self.assertTrue(released, "drip held slots past the absolute deadline")
        self.assertLess(elapsed, 1.0)

    def test_periodic_header_drip_releases_all_slots(self):
        prefix = (
            b"POST /api/v1/interactions HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"X-Pad: "
        )
        for _ in range(self.MAX_CONNECTIONS):
            self._start_drip(prefix)
        self.assertTrue(self._wait_until(self._occupied, 2), "slots never saturated")
        release_started = time.monotonic()
        released = self._wait_until(self._released, 2)
        elapsed = time.monotonic() - release_started
        self.assertTrue(released, "drip held slots past the absolute deadline")
        self.assertLess(elapsed, 1.0)

    def test_all_slots_released_and_server_remains_usable(self):
        for _ in range(self.MAX_CONNECTIONS):
            self._start_drip(b"G")
        self.assertTrue(self._wait_until(self._occupied, 2), "slots never saturated")
        self.assertTrue(self._wait_until(self._released, 2), "slots were not released")
        host, port = self.server.server_address
        with socket.create_connection((host, port), timeout=5) as connection:
            connection.sendall(
                b"GET /api/v1/health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
            )
            connection.settimeout(5)
            data = connection.recv(2048)
        self.assertTrue(data.startswith(b"HTTP/1."), "server did not respond")
        self.assertEqual(data.split(b" ", 2)[1], b"200")


class InteractionCompositionTests(unittest.TestCase):
    def test_interactions_cannot_be_mounted_without_interaction_only(self):
        registry = build_registry()
        service = build_service(
            SpyUnderstandingProvider(read_proposal()), registry=registry
        )
        with self.assertRaises(TypeError):
            RuntimeApiAdapter(
                RecordingRuntime(),
                ApiProjectionBuilder(registry),
                interaction_service=service,
                interaction_auth=InteractionAuth(TOKEN),
                interaction_only=False,
            )


def provider_with(*, body=None, transport_error=None, model="gemma-test"):
    return GemmaLocalUnderstandingProvider(
        GemmaUnderstandingProviderConfig(model),
        transport=StubGemmaUnderstandingTransport(body, error=transport_error),
    )


if __name__ == "__main__":
    unittest.main()
