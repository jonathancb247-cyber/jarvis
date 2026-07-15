import io
import os
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock
import unittest

from jarvis_core.ai_cloud import cli


class AICloudCliTests(unittest.TestCase):
    def test_missing_groq_key_fails_safely(self):
        output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(output):
                status = cli.main(["--config", "profiles/http-lab.example.json"])

        self.assertEqual(status, 1)
        text = output.getvalue()
        self.assertIn("Groq API key is not configured", text)
        self.assertNotIn("sk-", text)

    def test_cli_does_not_accept_api_key_argument(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.main(
                    [
                        "--config",
                        "profiles/http-lab.example.json",
                        "--api-key",
                        "fake",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
