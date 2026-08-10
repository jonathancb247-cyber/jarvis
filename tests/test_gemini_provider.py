import json
import os
import ssl
import unittest
from unittest.mock import patch

from jarvis_core.ai.adapter import FakeAIAdapter
from jarvis_core.ai.contracts import (
    AI_CONFIRMATION_REQUIRED,
    AI_MODEL_UNAVAILABLE,
    AI_PROVIDER_RATE_LIMITED,
    AI_PROVIDER_UNAUTHORIZED,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
)
from jarvis_core.ai.context import SafeContextBuilder
from jarvis_core.ai.gemini import (
    DEFAULT_GEMINI_MODEL,
    GEMINI_API_KEY_ENV,
    GEMINI_INTERACTIONS_PATH,
    GeminiAIProvider,
    GeminiHttpResponse,
    GeminiHttpsTransport,
    GeminiProviderConfig,
    GeminiProviderError,
    ai_action_plan_schema,
)
from jarvis_core.ai.transport_security import create_provider_ssl_context
from tests.test_ai_adapter import RecordingDriver, test_runtime


class GeminiConfigTests(unittest.TestCase):
    def test_valid_config_is_immutable_and_contains_no_key(self):
        config = GeminiProviderConfig()

        self.assertEqual(config.model, DEFAULT_GEMINI_MODEL)
        self.assertNotIn("key", repr(config).lower())
        with self.assertRaises(Exception):
            config.model = "gemini-3.1-flash-lite"

    def test_invalid_model_timeout_and_limits_are_rejected(self):
        invalid = [
            {"model": "gemini-flash-latest"},
            {"timeout_seconds": 0},
            {"maximum_request_bytes": 10},
            {"maximum_response_bytes": 10},
            {"maximum_output_tokens": 0},
        ]

        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    GeminiProviderConfig(**kwargs)

    def test_missing_api_key_is_safe_provider_error(self):
        with self.assertRaises(GeminiProviderError) as caught:
            GeminiAIProvider("", transport=FakeGeminiTransport(success_plan()))

        self.assertEqual(caught.exception.code, AI_PROVIDER_UNAUTHORIZED)

    def test_from_environment_uses_gemini_api_key_without_persisting_it(self):
        old = os.environ.pop(GEMINI_API_KEY_ENV, None)
        try:
            os.environ[GEMINI_API_KEY_ENV] = "fake-gemini-key"
            provider = GeminiAIProvider.from_environment(
                transport=FakeGeminiTransport(success_plan())
            )
        finally:
            if old is None:
                os.environ.pop(GEMINI_API_KEY_ENV, None)
            else:
                os.environ[GEMINI_API_KEY_ENV] = old

        self.assertEqual(provider.api_key, "fake-gemini-key")
        self.assertNotIn("fake-gemini-key", repr(provider.config))


class GeminiSchemaTests(unittest.TestCase):
    def test_full_ai_action_plan_schema_shape(self):
        schema = ai_action_plan_schema()

        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {
                "schema_version",
                "kind",
                "steps",
                "safe_summary",
                "clarification",
                "refusal",
                "confirmation_required",
                "policy_flags",
            },
        )
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 5)
        self.assertEqual(schema["properties"]["kind"]["enum"], ["clarify", "execute", "refuse"])

    def test_nested_step_clarification_and_refusal_are_closed(self):
        schema = ai_action_plan_schema()
        step = schema["properties"]["steps"]["items"]
        clarification = schema["properties"]["clarification"]
        refusal = schema["properties"]["refusal"]

        self.assertFalse(step["additionalProperties"])
        self.assertIn("safe_description", step["required"])
        self.assertEqual(clarification["type"], ["object", "null"])
        self.assertFalse(clarification["additionalProperties"])
        self.assertEqual(refusal["type"], ["object", "null"])
        self.assertFalse(refusal["additionalProperties"])


class GeminiProviderSuccessTests(unittest.TestCase):
    def test_provider_builds_interactions_request_without_secret_payload(self):
        transport = FakeGeminiTransport(success_plan())
        provider = GeminiAIProvider("fake-gemini-key", transport=transport)
        context = safe_context("Lee el estado de la lámpara.")

        payload = provider.generate_plan(context)
        request = transport.calls[0]["payload"]

        self.assertEqual(payload["kind"], "execute")
        self.assertEqual(transport.calls[0]["path"], GEMINI_INTERACTIONS_PATH)
        self.assertEqual(transport.calls[0]["headers"]["x-goog-api-key"], "fake-gemini-key")
        self.assertNotIn("fake-gemini-key", json.dumps(request))
        self.assertEqual(request["response_format"]["mime_type"], "application/json")
        self.assertEqual(request["generation_config"]["max_output_tokens"], 512)
        self.assertFalse(request["stream"])
        self.assertFalse(request["store"])

    def test_execute_read_plan_passes_existing_adapter_validation(self):
        provider = GeminiAIProvider(
            "fake-gemini-key",
            transport=FakeGeminiTransport(success_plan()),
        )
        adapter = FakeAIAdapter(test_runtime(), provider)

        result = adapter.propose("Lee el estado de la lámpara.")

        self.assertTrue(result.success)
        self.assertEqual(result.plan.steps[0].canonical_command_text, "device read lamp_1 status.read")

    def test_mutation_plan_still_requires_confirmation(self):
        driver = RecordingDriver()
        provider = GeminiAIProvider(
            "fake-gemini-key",
            transport=FakeGeminiTransport(
                success_plan("device apply lamp_1 power.switch state=true")
            ),
        )
        adapter = FakeAIAdapter(test_runtime(driver), provider)

        result = adapter.propose("Enciende la lámpara.")

        self.assertEqual(result.error, AI_CONFIRMATION_REQUIRED)
        self.assertEqual(driver.apply_calls, 0)

    def test_clarify_and_refuse_plans_do_not_execute(self):
        clarify = GeminiAIProvider(
            "fake-gemini-key",
            transport=FakeGeminiTransport(clarify_plan()),
        )
        refuse = GeminiAIProvider(
            "fake-gemini-key",
            transport=FakeGeminiTransport(refusal_plan()),
        )

        self.assertEqual(
            FakeAIAdapter(test_runtime(), clarify).propose("Enciende la luz.").status,
            "clarification_required",
        )
        self.assertEqual(
            FakeAIAdapter(test_runtime(), refuse).propose("Borra todos los archivos.").status,
            "refused",
        )

    def test_unknown_fields_are_rejected_by_existing_normalizer(self):
        payload = success_plan()
        decoded = json.loads(payload["steps"][0]["content"][0]["text"])
        decoded["provider_extra"] = "nope"
        payload["steps"][0]["content"][0]["text"] = json.dumps(decoded)
        provider = GeminiAIProvider("fake-gemini-key", transport=FakeGeminiTransport(payload))

        result = FakeAIAdapter(test_runtime(), provider).propose("extra")

        self.assertEqual(result.error, AI_RESPONSE_INVALID)


class GeminiProviderFailureTests(unittest.TestCase):
    def test_malformed_envelopes_and_output_are_safe_errors(self):
        cases = [
            {},
            {"status": "failed", "steps": []},
            {"status": "completed", "steps": []},
            {"status": "completed", "output_text": "not json"},
            {"status": "completed", "output_text": "[]"},
        ]
        for body in cases:
            with self.subTest(body=body):
                provider = GeminiAIProvider(
                    "fake-gemini-key",
                    transport=FakeGeminiTransport(body),
                )
                with self.assertRaises(GeminiProviderError) as caught:
                    provider.generate_plan(safe_context("test"))
                self.assertEqual(caught.exception.code, AI_RESPONSE_INVALID)

    def test_http_statuses_map_to_safe_errors(self):
        cases = [
            (401, AI_PROVIDER_UNAUTHORIZED),
            (403, AI_PROVIDER_UNAUTHORIZED),
            (429, AI_PROVIDER_RATE_LIMITED),
            (500, AI_MODEL_UNAVAILABLE),
        ]
        for status, code in cases:
            with self.subTest(status=status):
                provider = GeminiAIProvider(
                    "fake-gemini-key",
                    transport=FakeGeminiTransport({"error": "hidden"}, status=status),
                )
                with self.assertRaises(GeminiProviderError) as caught:
                    provider.generate_plan(safe_context("test"))
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("hidden", str(caught.exception))

    def test_oversized_response_and_timeout_are_safe_errors(self):
        provider = GeminiAIProvider(
            "fake-gemini-key",
            config=GeminiProviderConfig(maximum_response_bytes=1024),
            transport=FakeGeminiTransport(success_plan(), raise_error=GeminiProviderError(AI_RESPONSE_TOO_LARGE)),
        )

        with self.assertRaises(GeminiProviderError) as caught:
            provider.generate_plan(safe_context("test"))

        self.assertEqual(caught.exception.code, AI_RESPONSE_TOO_LARGE)

    def test_real_transport_rejects_non_fixed_path_without_network(self):
        with self.assertRaises(GeminiProviderError):
            GeminiHttpsTransport().post_json(
                "/v1beta/other",
                {},
                {},
                timeout_seconds=1,
                max_response_bytes=1024,
            )


class GeminiTransportSecurityTests(unittest.TestCase):
    def test_windows_provider_context_uses_truststore_without_global_injection(self):
        class FakeTruststore:
            called = []

            @staticmethod
            def SSLContext(protocol):
                FakeTruststore.called.append(protocol)
                return ssl.SSLContext(protocol)

        with patch("platform.system", return_value="Windows"):
            with patch.dict("sys.modules", {"truststore": FakeTruststore}):
                context = create_provider_ssl_context()

        self.assertEqual(FakeTruststore.called, [ssl.PROTOCOL_TLS_CLIENT])
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertFalse(hasattr(FakeTruststore, "inject_into_ssl"))

    def test_non_windows_provider_context_uses_stdlib_secure_default(self):
        sentinel = object()

        with patch("platform.system", return_value="Linux"):
            with patch("ssl.create_default_context", return_value=sentinel) as created:
                context = create_provider_ssl_context()

        self.assertIs(context, sentinel)
        created.assert_called_once_with()

    def test_transport_accepts_injected_secure_context(self):
        context = ssl.create_default_context()
        transport = GeminiHttpsTransport(ssl_context=context)

        self.assertIs(transport.ssl_context, context)
        self.assertEqual(transport.ssl_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(transport.ssl_context.check_hostname)


def safe_context(request):
    return SafeContextBuilder().build(request, test_runtime().context.device_registry)


def success_plan(command="device read lamp_1 status.read"):
    action_kind = "mutate" if " apply " in command else "read"
    return interaction_response(
        {
            "schema_version": 1,
            "kind": "execute",
            "steps": [
                {
                    "index": 0,
                    "canonical_command_text": command,
                    "safe_description": command,
                    "target_device_id": "lamp_1",
                    "capability_name": "power.switch" if "power.switch" in command else "status.read",
                    "action_kind": action_kind,
                    "requires_confirmation": action_kind == "mutate",
                    "policy_flags": [],
                }
            ],
            "safe_summary": "Plan seguro.",
            "clarification": None,
            "refusal": None,
            "confirmation_required": action_kind == "mutate",
            "policy_flags": [],
        }
    )


def clarify_plan():
    return interaction_response(
        {
            "schema_version": 1,
            "kind": "clarify",
            "steps": [],
            "safe_summary": "Falta elegir dispositivo.",
            "clarification": {
                "question": "¿Qué luz quieres usar?",
                "reason_code": "ambiguous_device",
                "missing_fields": ["device_id"],
                "candidate_options": ["lamp_1"],
            },
            "refusal": None,
            "confirmation_required": False,
            "policy_flags": [],
        }
    )


def refusal_plan():
    return interaction_response(
        {
            "schema_version": 1,
            "kind": "refuse",
            "steps": [],
            "safe_summary": "Solicitud rechazada.",
            "clarification": None,
            "refusal": {
                "safe_message": "No puedo realizar esa solicitud.",
                "reason_code": "forbidden_operation",
            },
            "confirmation_required": False,
            "policy_flags": [],
        }
    )


def interaction_response(plan):
    return {
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [{"type": "text", "text": json.dumps(plan)}],
            }
        ],
    }


class FakeGeminiTransport:
    def __init__(self, body, status=200, raise_error=None):
        self.body = body
        self.status = status
        self.raise_error = raise_error
        self.calls = []

    def post_json(self, path, payload, headers, timeout_seconds, max_response_bytes):
        self.calls.append(
            {
                "path": path,
                "payload": payload,
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        if self.raise_error is not None:
            raise self.raise_error
        return GeminiHttpResponse(self.status, self.body, headers=())


if __name__ == "__main__":
    unittest.main()
