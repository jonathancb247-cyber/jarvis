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
    InteractionAuth,
    LocalInteractionService,
)
from jarvis_core.api.projections import ApiProjectionBuilder
from jarvis_core.api.server import make_server
from jarvis_core.api.validation import MAX_INTERACTION_MESSAGE_LENGTH
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
        host, port = self.server.server_address
        with socket.create_connection((host, port), timeout=5) as connection:
            connection.sendall(request_bytes)
            connection.settimeout(5)
            data = connection.recv(2048)
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


def provider_with(*, body=None, transport_error=None, model="gemma-test"):
    return GemmaLocalUnderstandingProvider(
        GemmaUnderstandingProviderConfig(model),
        transport=StubGemmaUnderstandingTransport(body, error=transport_error),
    )


if __name__ == "__main__":
    unittest.main()
