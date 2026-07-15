import json
import ssl
import unittest
from unittest import mock

from jarvis_core.ai.adapter import FakeAIAdapter
from jarvis_core.ai.contracts import (
    AI_CONFIRMATION_REQUIRED,
    AI_PROVIDER_RATE_LIMITED,
    AI_PROVIDER_UNAUTHORIZED,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
)
from jarvis_core.ai.groq import (
    DEFAULT_GROQ_MODEL,
    GROQ_API_URL,
    GroqAIProvider,
    GroqHttpJsonTransport,
    GroqProviderConfig,
    build_groq_request,
    create_provider_ssl_context,
    decode_groq_response,
    groq_ai_action_plan_schema,
)
from jarvis_core.ai.provider import AIProviderError
from jarvis_core.bootstrap import build_http_runtime
from jarvis_core.devices import Device, DeviceCapability
from jarvis_core.drivers import DriverResult, SimulatedDriver


class GroqProviderConfigTests(unittest.TestCase):
    def test_valid_default_config(self):
        config = GroqProviderConfig()

        self.assertEqual(config.model, DEFAULT_GROQ_MODEL)
        self.assertEqual(config.timeout_seconds, 30)
        self.assertNotIn("api", repr(config).lower())

    def test_rejects_unapproved_model_and_invalid_limits(self):
        invalid_kwargs = [
            {"model": "openai/gpt-oss-120b"},
            {"timeout_seconds": 0},
            {"maximum_request_bytes": 0},
            {"maximum_response_bytes": 0},
            {"maximum_output_tokens": 0},
        ]
        for kwargs in invalid_kwargs:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    GroqProviderConfig(**kwargs)


class GroqTransportSecurityTests(unittest.TestCase):
    def test_transport_accepts_injected_secure_context(self):
        context = ssl.create_default_context()
        transport = GroqHttpJsonTransport(ssl_context=context)

        self.assertIs(transport.ssl_context, context)
        self.assertTrue(transport.ssl_context.check_hostname)
        self.assertEqual(transport.ssl_context.verify_mode, ssl.CERT_REQUIRED)

    def test_provider_context_preserves_verification(self):
        context = create_provider_ssl_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_windows_path_uses_truststore_without_global_injection(self):
        with mock.patch("platform.system", return_value="Windows"):
            with mock.patch("truststore.inject_into_ssl") as inject:
                context = create_provider_ssl_context()

        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        inject.assert_not_called()


class GroqStrictSchemaTests(unittest.TestCase):
    def test_schema_is_strict_and_requires_all_root_fields(self):
        schema = groq_ai_action_plan_schema()

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
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(schema["properties"]["steps"]["maxItems"], 5)

    def test_nested_objects_are_strict_and_nullable_fields_are_explicit(self):
        schema = groq_ai_action_plan_schema()
        step_schema = schema["properties"]["steps"]["items"]
        clarification = schema["properties"]["clarification"]
        refusal = schema["properties"]["refusal"]

        self.assertFalse(step_schema["additionalProperties"])
        self.assertIn("canonical_command_text", step_schema["required"])
        self.assertEqual(step_schema["properties"]["canonical_command_text"]["maxLength"], 512)
        self.assertEqual(clarification["anyOf"][1], {"type": "null"})
        self.assertEqual(refusal["anyOf"][1], {"type": "null"})
        self.assertFalse(clarification["anyOf"][0]["additionalProperties"])
        self.assertFalse(refusal["anyOf"][0]["additionalProperties"])


class GroqProviderRequestTests(unittest.TestCase):
    def test_request_uses_strict_structured_output_and_safe_options(self):
        context = test_context("Lee el estado de la lampara.")
        request = build_groq_request(context, GroqProviderConfig())

        self.assertEqual(request["model"], DEFAULT_GROQ_MODEL)
        self.assertFalse(request["stream"])
        self.assertEqual(request["temperature"], 0)
        self.assertEqual(request["max_completion_tokens"], 256)
        self.assertEqual(request["response_format"]["type"], "json_schema")
        self.assertTrue(request["response_format"]["json_schema"]["strict"])
        self.assertNotIn("10.255", json.dumps(request))
        self.assertIn("canonical commands", request["messages"][0]["content"].lower())

    def test_provider_rejects_missing_api_key(self):
        with self.assertRaises(AIProviderError) as raised:
            GroqAIProvider(api_key="")

        self.assertEqual(raised.exception.code, AI_PROVIDER_UNAUTHORIZED)

    def test_provider_posts_to_fake_transport_and_returns_raw_plan(self):
        provider = GroqAIProvider(
            api_key="fake-test-key",
            transport=FakeGroqTransport(valid_execute_plan()),
        )

        plan = provider.generate_plan(test_context("Lee el estado de la lampara."))

        self.assertEqual(plan["kind"], "execute")
        self.assertEqual(plan["steps"][0]["canonical_command_text"], "device read lamp_1 status.read")

    def test_provider_maps_transport_errors_without_raw_payload(self):
        provider = GroqAIProvider(
            api_key="fake-test-key",
            transport=FailingTransport(AI_PROVIDER_RATE_LIMITED),
        )

        with self.assertRaises(AIProviderError) as raised:
            provider.generate_plan(test_context("Lee el estado."))

        self.assertEqual(raised.exception.code, AI_PROVIDER_RATE_LIMITED)
        self.assertNotIn("fake-test-key", str(raised.exception))

    def test_decode_rejects_invalid_envelopes_and_content(self):
        invalid_envelopes = [
            {},
            {"choices": []},
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": "{broken"}}]},
            {"choices": [{"message": {"content": "[]"}}]},
        ]
        for envelope in invalid_envelopes:
            with self.subTest(envelope=envelope):
                with self.assertRaises(AIProviderError) as raised:
                    decode_groq_response(envelope)
                self.assertEqual(raised.exception.code, AI_RESPONSE_INVALID)


class GroqAdapterIntegrationTests(unittest.TestCase):
    def test_valid_execute_plan_passes_existing_validator(self):
        adapter = FakeAIAdapter(
            test_runtime(),
            provider=GroqAIProvider(
                api_key="fake-test-key",
                transport=FakeGroqTransport(valid_execute_plan()),
            ),
        )

        result = adapter.propose("Lee el estado de la lampara.")

        self.assertTrue(result.success)
        self.assertEqual(result.plan.steps[0].canonical_command_text, "device read lamp_1 status.read")

    def test_mutation_still_requires_confirmation(self):
        driver = RecordingDriver()
        adapter = FakeAIAdapter(
            test_runtime(driver),
            provider=GroqAIProvider(
                api_key="fake-test-key",
                transport=FakeGroqTransport(valid_mutation_plan()),
            ),
        )

        result = adapter.propose("Enciende la lampara.")

        self.assertFalse(result.success)
        self.assertEqual(result.error, AI_CONFIRMATION_REQUIRED)
        self.assertEqual(driver.apply_calls, 0)

    def test_clarification_and_refusal_pass_through_safely(self):
        clarification = FakeAIAdapter(
            test_runtime(),
            provider=GroqAIProvider(
                api_key="fake-test-key",
                transport=FakeGroqTransport(valid_clarify_plan()),
            ),
        ).propose("Enciende la luz.")
        refusal = FakeAIAdapter(
            test_runtime(),
            provider=GroqAIProvider(
                api_key="fake-test-key",
                transport=FakeGroqTransport(valid_refusal_plan()),
            ),
        ).propose("Borra todos los archivos.")

        self.assertEqual(clarification.status, "clarification_required")
        self.assertEqual(refusal.status, "refused")

    def test_broad_wrapper_is_not_repaired(self):
        adapter = FakeAIAdapter(
            test_runtime(),
            provider=GroqAIProvider(
                api_key="fake-test-key",
                transport=FakeGroqTransport({"wrapper": valid_execute_plan()}),
            ),
        )

        result = adapter.propose("Lee el estado.")

        self.assertFalse(result.success)
        self.assertEqual(result.error, AI_RESPONSE_INVALID)

    def test_provider_errors_map_to_adapter_errors(self):
        adapter = FakeAIAdapter(
            test_runtime(),
            provider=GroqAIProvider(
                api_key="fake-test-key",
                transport=FailingTransport(AI_RESPONSE_TOO_LARGE),
            ),
        )

        result = adapter.propose("Lee el estado.")

        self.assertFalse(result.success)
        self.assertEqual(result.error, AI_RESPONSE_TOO_LARGE)


class FakeGroqTransport:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def post_json(self, payload, api_key, timeout_seconds, maximum_response_bytes):
        self.calls.append(
            {
                "payload": payload,
                "api_key": api_key,
                "timeout_seconds": timeout_seconds,
                "maximum_response_bytes": maximum_response_bytes,
            }
        )
        self.assert_safe_payload(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(self.plan),
                    }
                }
            ]
        }

    def assert_safe_payload(self, payload):
        self_string = json.dumps(payload)
        assert GROQ_API_URL not in self_string
        assert "Authorization" not in self_string


class FailingTransport:
    def __init__(self, code):
        self.code = code

    def post_json(self, payload, api_key, timeout_seconds, maximum_response_bytes):
        raise AIProviderError(self.code)


class RecordingDriver(SimulatedDriver):
    def __init__(self):
        super().__init__()
        self.apply_calls = 0
        self.set_reading("lamp_1", "status.read", {"power": False})

    def apply(self, device, capability_name, parameters):
        self.apply_calls += 1
        return DriverResult(True, {"power": parameters.get("state") == "true"}, None)


def test_context(user_request):
    return FakeAIAdapter(test_runtime()).context_builder.build(
        user_request,
        test_runtime().context.device_registry,
    )


def test_runtime(driver=None):
    return build_http_runtime(driver or RecordingDriver(), devices=[lamp()])


def lamp():
    return Device(
        id="lamp_1",
        name="Lamp",
        type="light",
        capabilities=[
            DeviceCapability(
                name="power.switch",
                kind="action",
                parameters={"state": {"type": "string", "required": True}},
            ),
            DeviceCapability(
                name="status.read",
                kind="reading",
                parameters={},
            ),
        ],
    )


def valid_execute_plan():
    return {
        "schema_version": 1,
        "kind": "execute",
        "steps": [
            {
                "index": 0,
                "canonical_command_text": "device read lamp_1 status.read",
                "safe_description": "Leer estado.",
                "target_device_id": "lamp_1",
                "capability_name": "status.read",
                "action_kind": "read",
                "requires_confirmation": False,
                "policy_flags": [],
            }
        ],
        "safe_summary": "Leer estado.",
        "clarification": None,
        "refusal": None,
        "confirmation_required": False,
        "policy_flags": [],
    }


def valid_mutation_plan():
    plan = valid_execute_plan()
    plan["steps"][0].update(
        {
            "canonical_command_text": "device apply lamp_1 power.switch state=true",
            "safe_description": "Encender lampara.",
            "capability_name": "power.switch",
            "action_kind": "mutate",
            "requires_confirmation": True,
        }
    )
    plan["safe_summary"] = "Encender lampara."
    plan["confirmation_required"] = True
    return plan


def valid_clarify_plan():
    return {
        "schema_version": 1,
        "kind": "clarify",
        "steps": [],
        "safe_summary": "Necesito mas informacion.",
        "clarification": {
            "question": "Que luz quieres controlar?",
            "reason_code": "ambiguous_device",
            "missing_fields": ["device_id"],
            "candidate_options": ["lamp_1"],
        },
        "refusal": None,
        "confirmation_required": False,
        "policy_flags": [],
    }


def valid_refusal_plan():
    return {
        "schema_version": 1,
        "kind": "refuse",
        "steps": [],
        "safe_summary": "Solicitud rechazada.",
        "clarification": None,
        "refusal": {
            "safe_message": "No puedo realizar esa solicitud.",
            "reason_code": "unsafe_request",
        },
        "confirmation_required": False,
        "policy_flags": [],
    }


if __name__ == "__main__":
    unittest.main()
