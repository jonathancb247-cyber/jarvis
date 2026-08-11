import os
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO

from jarvis_core.ai_cloud.cli import main
from jarvis_core.ai.gemini import GEMINI_API_KEY_ENV
from tests.test_runtime_api import write_profile


class AICloudEntryPointTests(unittest.TestCase):
    def test_missing_key_is_safe_startup_error(self):
        old = os.environ.pop(GEMINI_API_KEY_ENV, None)
        output = []
        try:
            with tempfile.TemporaryDirectory() as temp:
                config = write_profile(temp_path(temp), "state/http-lab.state.json")
                result = main(
                    ["--config", str(config), "--provider", "gemini"],
                    input_fn=lambda prompt: "exit",
                    output_fn=output.append,
                )
        finally:
            if old is not None:
                os.environ[GEMINI_API_KEY_ENV] = old

        self.assertEqual(result, 1)
        self.assertEqual(output, ["Gemini provider is unavailable."])

    def test_key_is_not_accepted_as_cli_argument(self):
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main(
                    [
                        "--config",
                        "profiles/http-lab.example.json",
                        "--provider",
                        "gemini",
                        "--api-key",
                        "fake",
                    ],
                    input_fn=lambda prompt: "exit",
                    output_fn=lambda text: None,
                )


def temp_path(value):
    from pathlib import Path

    return Path(value)


if __name__ == "__main__":
    unittest.main()
