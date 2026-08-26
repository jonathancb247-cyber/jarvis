import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jarvis_core.ai_local.cli import main
from tests.test_runtime_api import write_profile


class AILocalEntryPointTests(unittest.TestCase):
    def test_startup_does_not_probe_ollama_server(self):
        output = []
        with tempfile.TemporaryDirectory() as temp:
            config = write_profile(Path(temp), "state/http-lab.state.json")
            result = main(
                ["--config", str(config), "--provider", "ollama", "--model", "qwen3:4b"],
                input_fn=lambda prompt: "exit",
                output_fn=output.append,
            )

        self.assertEqual(result, 0)
        self.assertEqual(output, ["JarvisOS AI local listening with provider ollama.", "Bye."])

    def test_model_is_required_and_no_api_key_argument_exists(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main(
                    ["--config", "profiles/http-lab.example.json", "--provider", "ollama"],
                    input_fn=lambda prompt: "exit",
                    output_fn=lambda text: None,
                )
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main(
                    [
                        "--config",
                        "profiles/http-lab.example.json",
                        "--provider",
                        "ollama",
                        "--model",
                        "qwen3:4b",
                        "--api-key",
                        "fake",
                    ],
                    input_fn=lambda prompt: "exit",
                    output_fn=lambda text: None,
                )

    def test_non_localhost_host_is_rejected_by_parser(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main(
                    [
                        "--config",
                        "profiles/http-lab.example.json",
                        "--provider",
                        "ollama",
                        "--model",
                        "qwen3:4b",
                        "--host",
                        "192.168.1.10",
                    ],
                    input_fn=lambda prompt: "exit",
                    output_fn=lambda text: None,
                )

    def test_successful_loop_uses_injected_fake_provider(self):
        output = []

        class FakeProvider:
            def __init__(self, config):
                self.config = config

            def generate_plan(self, context):
                return {
                    "schema_version": 1,
                    "kind": "execute",
                    "steps": [
                        {
                            "index": 0,
                            "canonical_command_text": "device read lamp_1 status.read",
                            "safe_description": "read",
                            "target_device_id": "lamp_1",
                            "capability_name": "status.read",
                            "action_kind": "read",
                            "requires_confirmation": False,
                            "policy_flags": [],
                        }
                    ],
                    "safe_summary": "read",
                    "clarification": None,
                    "refusal": None,
                    "confirmation_required": False,
                    "policy_flags": [],
                }

        with tempfile.TemporaryDirectory() as temp:
            config = write_profile(Path(temp), "state/http-lab.state.json")
            inputs = iter(["exit"])
            with patch("jarvis_core.ai_local.cli.OllamaAIProvider", FakeProvider):
                result = main(
                    ["--config", str(config), "--provider", "ollama", "--model", "qwen3:4b"],
                    input_fn=lambda prompt: next(inputs),
                    output_fn=output.append,
                )

        self.assertEqual(result, 0)
        self.assertEqual(output, ["JarvisOS AI local listening with provider ollama.", "Bye."])


if __name__ == "__main__":
    unittest.main()
