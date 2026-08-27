import json
import unittest

from jarvis_core.ai.adapter import FakeAIAdapter
from jarvis_core.ai.contracts import (
    AI_CONFIRMATION_REQUIRED,
    AI_MODEL_NOT_FOUND,
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
)
from jarvis_core.ai.context import SafeContextBuilder
from jarvis_core.ai.ollama import (
    OLLAMA_CHAT_PATH,
    OllamaAIProvider,
    OllamaHttpResponse,
    OllamaHttpTransport,
    OllamaProviderConfig,
    OllamaProviderError,
)
from tests.test_ai_adapter import RecordingDriver, test_runtime


class OllamaConfigTests(unittest.TestCase):
    def test_config_is_localhost_only_and_requires_model(self):
        config = OllamaProviderConfig(model="qwen3:4b")

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 11434)
        with self.assertRaises(ValueError):
            OllamaProviderConfig(model="")
        with self.assertRaises(ValueError):
            OllamaProviderConfig(model="qwen3:4b", host="192.168.1.10")

    def test_transport_rejects_non_fixed_path_without_network(self):
        with self.assertRaises(OllamaProviderError) as raised:
            OllamaHttpTransport().post_json(
                "127.0.0.1",
                11434,
                "/api/generate",
                {},
                timeout_seconds=1,
                max_response_bytes=1024,
            )

        self.assertEqual(raised.exception.code, AI_PROVIDER_PROTOCOL_ERROR)


class OllamaProviderTests(unittest.TestCase):
    def test_provider_builds_localhost_chat_request_with_schema(self):
        transport = FakeOllamaTransport(ollama_response(success_plan()))
        provider = OllamaAIProvider(OllamaProviderConfig(model="qwen3:4b"), transport=transport)

        payload = provider.generate_plan(safe_context("Lee la lampara."))
        request = transport.calls[0]["payload"]

        self.assertEqual(payload["kind"], "execute")
        self.assertEqual(transport.calls[0]["host"], "127.0.0.1")
        self.assertEqual(transport.calls[0]["path"], OLLAMA_CHAT_PATH)
        self.assertFalse(request["stream"])
        self.assertIs(request["think"], False)
        self.assertEqual(request["model"], "qwen3:4b")
        self.assertEqual(request["format"]["type"], "object")
        self.assertNotIn("think", request["options"])
        self.assertEqual(request["options"]["temperature"], 0)
        self.assertEqual(request["options"]["num_predict"], 512)
        self.assertEqual(len(request["messages"]), 2)
        self.assertEqual(request["messages"][0]["role"], "system")
        self.assertEqual(request["messages"][1]["role"], "user")
        self.assertNotIn("api_key", json.dumps(request).lower())

    def test_read_plan_passes_existing_adapter_validation(self):
        provider = OllamaAIProvider(
            OllamaProviderConfig(model="qwen3:4b"),
            transport=FakeOllamaTransport(ollama_response(success_plan())),
        )

        result = FakeAIAdapter(test_runtime(), provider).propose("Lee el estado.")

        self.assertTrue(result.success)
        self.assertEqual(result.plan.steps[0].canonical_command_text, "device read lamp_1 status.read")

    def test_mutation_plan_still_requires_confirmation(self):
        driver = RecordingDriver()
        provider = OllamaAIProvider(
            OllamaProviderConfig(model="qwen3:4b"),
            transport=FakeOllamaTransport(
                ollama_response(success_plan("device apply lamp_1 power.switch state=true"))
            ),
        )

        result = FakeAIAdapter(test_runtime(driver), provider).propose("Enciende la lampara.")

        self.assertEqual(result.error, AI_CONFIRMATION_REQUIRED)
        self.assertEqual(driver.apply_calls, 0)

    def test_malformed_output_is_safe_error(self):
        provider = OllamaAIProvider(
            OllamaProviderConfig(model="qwen3:4b"),
            transport=FakeOllamaTransport({"message": {"content": "not json"}}),
        )

        with self.assertRaises(OllamaProviderError) as raised:
            provider.generate_plan(safe_context("test"))

        self.assertEqual(raised.exception.code, AI_RESPONSE_INVALID)

    def test_http_statuses_map_to_safe_errors(self):
        cases = [(404, AI_MODEL_NOT_FOUND), (500, "ai_model_unavailable")]
        for status, code in cases:
            with self.subTest(status=status):
                provider = OllamaAIProvider(
                    OllamaProviderConfig(model="qwen3:4b"),
                    transport=FakeOllamaTransport({"error": "hidden"}, status=status),
                )
                with self.assertRaises(OllamaProviderError) as raised:
                    provider.generate_plan(safe_context("test"))
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("hidden", str(raised.exception))

    def test_transport_unavailable_is_safe(self):
        provider = OllamaAIProvider(
            OllamaProviderConfig(model="qwen3:4b"),
            transport=FailingOllamaTransport(),
        )

        with self.assertRaises(OllamaProviderError) as raised:
            provider.generate_plan(safe_context("test"))

        self.assertEqual(raised.exception.code, AI_PROVIDER_UNAVAILABLE)


def safe_context(request):
    return SafeContextBuilder().build(request, test_runtime().context.device_registry)


def success_plan(command="device read lamp_1 status.read"):
    action_kind = "mutate" if " apply " in command else "read"
    return {
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


def ollama_response(plan):
    return {"message": {"role": "assistant", "content": json.dumps(plan)}, "done": True}


class FakeOllamaTransport:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status
        self.calls = []

    def post_json(self, host, port, path, payload, timeout_seconds, max_response_bytes):
        self.calls.append(
            {
                "host": host,
                "port": port,
                "path": path,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        return OllamaHttpResponse(self.status, self.body)


class FailingOllamaTransport:
    def post_json(self, host, port, path, payload, timeout_seconds, max_response_bytes):
        raise OllamaProviderError(AI_PROVIDER_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
