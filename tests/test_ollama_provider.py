import json
import unittest

from jarvis_core.ai import FakeAIAdapter
from jarvis_core.ai.contracts import (
    AI_CONFIRMATION_REQUIRED,
    AI_MODEL_NOT_FOUND,
    AI_MODEL_UNAVAILABLE,
    AI_PROVIDER_PROTOCOL_ERROR,
    AI_PROVIDER_TIMEOUT,
    AI_PROVIDER_UNAVAILABLE,
    AI_RESPONSE_INVALID,
    AI_RESPONSE_TOO_LARGE,
)
from jarvis_core.ai.context import SafeContextBuilder
from jarvis_core.ai.fake_provider import execute_plan, step
from jarvis_core.ai.ollama import (
    OLLAMA_GENERATE_PATH,
    OllamaAIProvider,
    OllamaProviderConfig,
    OllamaProviderError,
    build_ollama_request,
    decode_ollama_envelope,
)
from jarvis_core.bootstrap import build_http_runtime, build_runtime
from jarvis_core.devices import Device, DeviceCapability
from jarvis_core.drivers import DriverResult, SimulatedDriver


class OllamaProviderConfigTests(unittest.TestCase):
    def test_valid_default_config_is_localhost_only(self):
        config = OllamaProviderConfig(model="qwen3:1.7b")

        self.assertEqual(config.model, "qwen3:1.7b")
        self.assertEqual(config.base_url, "http://127.0.0.1:11434")
        self.assertEqual(config.timeout_seconds, 30)

    def test_localhost_is_normalized(self):
        config = OllamaProviderConfig(
            model="qwen3:4b",
            base_url="http://localhost:11434",
        )

        self.assertEqual(config.base_url, "http://127.0.0.1:11434")

    def test_rejects_non_localhost_urls(self):
        invalid_urls = [
            "http://0.0.0.0:11434",
            "http://192.168.1.10:11434",
            "http://example.com:11434",
            "http://ollama.local:11434",
            "https://127.0.0.1:11434",
            "http://user:pass@127.0.0.1:11434",
            "http://127.0.0.1:11434/api/generate",
            "http://127.0.0.1:11434?debug=true",
            "http://127.0.0.1:11434#fragment",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    OllamaProviderConfig(model="qwen3:1.7b", base_url=url)

    def test_rejects_invalid_model_timeout_and_response_size(self):
        with self.assertRaises(ValueError):
            OllamaProviderConfig(model="../qwen")
        with self.assertRaises(ValueError):
            OllamaProviderConfig(model="qwen3:1.7b", timeout_seconds=0)
        with self.assertRaises(ValueError):
            OllamaProviderConfig(model="qwen3:1.7b", maximum_response_bytes=0)


class OllamaProviderRequestTests(unittest.TestCase):
    def test_request_contains_spanish_request_and_safe_context_only(self):
        context = SafeContextBuilder().build("Enciende la lampara.", test_runtime().context.device_registry)
        request = build_ollama_request(OllamaProviderConfig(model="qwen3:1.7b"), context)
        prompt = request["prompt"]

        self.assertEqual(request["model"], "qwen3:1.7b")
        self.assertFalse(request["stream"])
        self.assertEqual(request["format"], "json")
        self.assertIn("Enciende la lampara.", prompt)
        self.assertIn("device apply lamp_1 power.switch state=true", prompt)
        self.assertNotIn("http://", prompt)
        self.assertNotIn("RuntimeContext", prompt)
        self.assertNotIn("DriverResult", prompt)

    def test_provider_returns_raw_plan_payload(self):
        raw_plan = execute_plan(
            "Read lamp status.",
            [step(0, "device read lamp_1 status.read", "Read lamp status.", "lamp_1", "status.read", "read")],
        )
        transport = FakeOllamaTransport(raw_plan)
        provider = OllamaAIProvider(OllamaProviderConfig(model="qwen3:1.7b"), transport)
        context = SafeContextBuilder().build("Lee el estado de la lampara.", test_runtime().context.device_registry)

        result = provider.generate_plan(context)

        self.assertEqual(result, raw_plan)
        self.assertEqual(transport.calls[0]["path"], OLLAMA_GENERATE_PATH)

    def test_spanish_read_only_request_executes_through_existing_adapter(self):
        raw_plan = execute_plan(
            "Read lamp status.",
            [step(0, "device read lamp_1 status.read", "Read lamp status.", "lamp_1", "status.read", "read")],
        )
        provider = OllamaAIProvider(
            OllamaProviderConfig(model="qwen3:1.7b"),
            FakeOllamaTransport(raw_plan),
        )
        runtime = test_runtime()
        adapter = FakeAIAdapter(runtime, provider=provider)

        result = adapter.propose("Lee el estado de la lampara.")

        self.assertTrue(result.success)
        self.assertEqual(result.plan.steps[0].canonical_command_text, "device read lamp_1 status.read")

    def test_spanish_mutation_requires_confirmation(self):
        raw_plan = execute_plan(
            "Turn lamp on.",
            [
                step(
                    0,
                    "device apply lamp_1 power.switch state=true",
                    "Turn lamp on.",
                    "lamp_1",
                    "power.switch",
                    "mutate",
                )
            ],
        )
        driver = RecordingDriver()
        adapter = FakeAIAdapter(
            test_runtime(driver),
            provider=OllamaAIProvider(
                OllamaProviderConfig(model="qwen3:1.7b"),
                FakeOllamaTransport(raw_plan),
            ),
        )

        proposed = adapter.propose("Enciende la lampara.")
        plan_id = adapter.confirmation_store.pending.pending_plan_id
        confirmed = adapter.confirm(plan_id)

        self.assertEqual(proposed.error, AI_CONFIRMATION_REQUIRED)
        self.assertEqual(driver.apply_calls, 1)
        self.assertTrue(confirmed.success)

    def test_spanish_catalog_request_uses_english_command(self):
        raw_plan = execute_plan(
            "List devices.",
            [step(0, "device list", "List devices.", None, None, "read")],
        )
        adapter = FakeAIAdapter(
            test_runtime(),
            provider=OllamaAIProvider(
                OllamaProviderConfig(model="qwen3:1.7b"),
                FakeOllamaTransport(raw_plan),
            ),
        )

        result = adapter.propose("Que dispositivos tienes?")

        self.assertTrue(result.success)
        self.assertEqual(result.plan.steps[0].canonical_command_text, "device list")

    def test_provider_error_maps_to_safe_adapter_error(self):
        adapter = FakeAIAdapter(
            test_runtime(),
            provider=OllamaAIProvider(
                OllamaProviderConfig(model="qwen3:1.7b"),
                FailingOllamaTransport(AI_PROVIDER_TIMEOUT),
            ),
        )

        result = adapter.propose("Lee el estado de la lampara.")

        self.assertFalse(result.success)
        self.assertEqual(result.error, AI_PROVIDER_TIMEOUT)
        self.assertNotIn("127.0.0.1", result.message)


class OllamaEnvelopeTests(unittest.TestCase):
    def test_decode_valid_generate_and_chat_envelopes(self):
        plan = execute_plan(
            "Read lamp.",
            [step(0, "device read lamp_1 status.read", "Read lamp.")],
        )

        self.assertEqual(decode_ollama_envelope({"response": json.dumps(plan)}), plan)
        self.assertEqual(
            decode_ollama_envelope({"message": {"content": json.dumps(plan)}}),
            plan,
        )

    def test_decode_rejects_malformed_or_empty_output(self):
        invalid = [
            {},
            {"response": ""},
            {"response": "not-json"},
            {"response": "[]"},
        ]
        for envelope in invalid:
            with self.subTest(envelope=envelope):
                with self.assertRaises(OllamaProviderError) as error:
                    decode_ollama_envelope(envelope)
                self.assertEqual(error.exception.code, AI_RESPONSE_INVALID)

    def test_decode_maps_safe_ollama_errors(self):
        cases = [
            ({"error": "model not found"}, AI_MODEL_NOT_FOUND),
            ({"error": "model is loading"}, AI_MODEL_UNAVAILABLE),
            ({"error": "unexpected"}, AI_PROVIDER_PROTOCOL_ERROR),
        ]
        for envelope, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(OllamaProviderError) as error:
                    decode_ollama_envelope(envelope)
                self.assertEqual(error.exception.code, code)

    def test_decode_rejects_oversized_response(self):
        with self.assertRaises(OllamaProviderError) as error:
            decode_ollama_envelope({"response": '{"x":"' + ("a" * 100) + '"}'}, 16)

        self.assertEqual(error.exception.code, AI_RESPONSE_TOO_LARGE)


class OllamaBoundaryRegressionTests(unittest.TestCase):
    def test_default_runtime_remains_provider_free(self):
        runtime = build_runtime()

        self.assertFalse(hasattr(runtime, "ai_adapter"))
        self.assertFalse(hasattr(runtime, "ollama_provider"))

    def test_provider_does_not_call_runtime_planner_driver_registry_or_state_store(self):
        raw_plan = execute_plan(
            "Read lamp status.",
            [step(0, "device read lamp_1 status.read", "Read lamp status.")],
        )
        provider = OllamaAIProvider(
            OllamaProviderConfig(model="qwen3:1.7b"),
            FakeOllamaTransport(raw_plan),
        )
        context = SafeContextBuilder().build("Lee el estado.", test_runtime().context.device_registry)

        result = provider.generate_plan(context)

        self.assertEqual(result["steps"][0]["canonical_command_text"], "device read lamp_1 status.read")

    def test_transport_failures_are_normalized_without_raw_details(self):
        for code in (AI_PROVIDER_UNAVAILABLE, AI_PROVIDER_TIMEOUT):
            with self.subTest(code=code):
                provider = OllamaAIProvider(
                    OllamaProviderConfig(model="qwen3:1.7b"),
                    FailingOllamaTransport(code),
                )
                context = SafeContextBuilder().build("Lee el estado.", test_runtime().context.device_registry)

                with self.assertRaises(OllamaProviderError) as error:
                    provider.generate_plan(context)

                self.assertEqual(error.exception.code, code)


class FakeOllamaTransport:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def post_json(self, base_url, path, payload, timeout_seconds, maximum_response_bytes):
        self.calls.append(
            {
                "base_url": base_url,
                "path": path,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
                "maximum_response_bytes": maximum_response_bytes,
            }
        )
        return {"response": json.dumps(self.plan)}


class FailingOllamaTransport:
    def __init__(self, code):
        self.code = code

    def post_json(self, base_url, path, payload, timeout_seconds, maximum_response_bytes):
        raise OllamaProviderError(self.code)


class RecordingDriver(SimulatedDriver):
    def __init__(self):
        super().__init__()
        self.apply_calls = 0
        self.set_reading("lamp_1", "status.read", {"power": True})

    def apply(self, device, capability_name, parameters):
        self.apply_calls += 1
        return DriverResult(True, {"power": parameters.get("state") == "true"}, None)


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


if __name__ == "__main__":
    unittest.main()

