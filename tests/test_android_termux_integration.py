"""Guards for the experimental Android/Termux integration assets.

These tests validate the committed, device-independent pieces of the
Android/Termux runbook: the example profile, the token tool, the strict
interaction-response checker and the Termux scripts. They do not touch a device,
do not require network access and run on any platform.
"""

import http.server
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.configuration import RuntimeConfigurationLoader


REPO_ROOT = Path(__file__).resolve().parents[1]
TERMUX_DIR = REPO_ROOT / "tools" / "termux"
PROFILE_PATH = REPO_ROOT / "profiles" / "android-termux.example.json"
TOKEN_SCRIPT = TERMUX_DIR / "make_interaction_token.py"
CHECKER = TERMUX_DIR / "check_interaction_response.py"
INTEGRATION_DOC = (
    REPO_ROOT / "docs" / "integration" / "ANDROID_TERMUX_MACRODROID.md"
)


class AndroidTermuxProfileTests(unittest.TestCase):
    def test_example_profile_is_valid(self):
        profile = RuntimeConfigurationLoader().load(PROFILE_PATH)
        self.assertEqual(profile.schema_version, 1)
        self.assertEqual(profile.name, "android-termux-lab")
        self.assertTrue(profile.devices)
        self.assertEqual(profile.http_bindings, ())
        self.assertEqual(profile.mqtt_bindings, ())
        self.assertNotIn("state_store_path", profile.runtime_options)

    def test_example_profile_has_no_endpoints_or_secrets(self):
        text = PROFILE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("://", text)
        self.assertNotIn("state_store_path", text)
        lowered = text.lower()
        for forbidden in ("token", "secret", "password", "ssid"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_example_profile_builds_offline_runtime(self):
        runtime = build_runtime_from_config(PROFILE_PATH)
        device = runtime.context.device_registry.get("lamp_1")
        self.assertIsNotNone(device)
        self.assertEqual(device.id, "lamp_1")


class InteractionResponseCheckerTests(unittest.TestCase):
    def _run(self, text, *arguments):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "response.json"
            target.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(CHECKER), "--file", str(target), *arguments],
                capture_output=True,
                text=True,
            )

    def test_accepts_root_level_false(self):
        result = self._run(
            '{"type": "conversation", "success": true, "commands_executed": false}',
            "--type",
            "conversation",
            "--expect-success",
            "true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_nested_false_with_root_true(self):
        # The exact regression the audit requested: a nested false must not mask
        # a root true.
        result = self._run(
            '{"decision": {"commands_executed": false}, "commands_executed": true}'
        )
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_root_field(self):
        result = self._run('{"type": "conversation", "success": true}')
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_string_false(self):
        result = self._run('{"commands_executed": "false"}')
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_numeric_zero(self):
        result = self._run('{"commands_executed": 0}')
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_malformed_json(self):
        result = self._run('{"commands_executed": false')
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_wrong_type(self):
        result = self._run(
            '{"type": "understanding", "commands_executed": false}',
            "--type",
            "conversation",
        )
        self.assertNotEqual(result.returncode, 0)


class SimulatedServerValidationTests(unittest.TestCase):
    def test_checker_rejects_crafted_server_response(self):
        body = (
            b'{"type":"conversation","success":true,'
            b'"decision":{"commands_executed":false},'
            b'"commands_executed":true}'
        )

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # keep test output quiet
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/api/v1/interactions"
            with urllib.request.urlopen(url, timeout=5) as response:
                captured = response.read()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "captured.json"
            target.write_bytes(captured)
            result = subprocess.run(
                [sys.executable, str(CHECKER), "--file", str(target)],
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)


class AndroidTermuxTokenToolTests(unittest.TestCase):
    def _run(self, *arguments):
        return subprocess.run(
            [sys.executable, str(TOKEN_SCRIPT), *arguments],
            capture_output=True,
            text=True,
        )

    def test_writes_valid_token_without_printing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "interaction.token"
            result = self._run("--path", str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            token = target.read_text(encoding="utf-8").strip()
            self.assertGreaterEqual(len(token), 16)
            self.assertTrue(token.isascii())
            self.assertTrue(token.isprintable())
            self.assertFalse(any(character.isspace() for character in token))
            self.assertNotIn(token, result.stdout)
            self.assertNotIn(token, result.stderr)

    def test_is_idempotent_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "interaction.token"
            self._run("--path", str(target))
            first = target.read_text(encoding="utf-8")
            self._run("--path", str(target))
            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_rejects_invalid_existing_token_without_force(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "interaction.token"
            target.write_text("short", encoding="ascii")
            result = self._run("--path", str(target))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(encoding="ascii"), "short")

    def test_force_replaces_invalid_existing_token(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "interaction.token"
            target.write_text("short", encoding="ascii")
            result = self._run("--path", str(target), "--force")
            self.assertEqual(result.returncode, 0, result.stderr)
            replacement = target.read_text(encoding="utf-8").strip()
            self.assertNotEqual(replacement, "short")
            self.assertGreaterEqual(len(replacement), 16)


class AndroidTermuxScriptTests(unittest.TestCase):
    def test_termux_scripts_exist(self):
        for name in (
            "bootstrap_termux.sh",
            "run_core_interaction.sh",
            "smoke_interaction.sh",
            "check_interaction_response.py",
        ):
            with self.subTest(name=name):
                self.assertTrue((TERMUX_DIR / name).is_file())

    def test_core_runner_is_interaction_only_and_reads_token_from_file(self):
        text = (TERMUX_DIR / "run_core_interaction.sh").read_text(encoding="utf-8")
        self.assertIn("--interaction-only", text)
        self.assertIn("JARVIS_API_INTERACTION_TOKEN", text)
        self.assertIn('"$TOKEN_FILE"', text)
        self.assertIn("127.0.0.1", text)
        self.assertIn("non-loopback host", text)

    def test_smoke_uses_strict_checker_and_hardens_requests(self):
        text = (TERMUX_DIR / "smoke_interaction.sh").read_text(encoding="utf-8")
        self.assertIn("/api/v1/interactions", text)
        self.assertIn("/api/v1/commands", text)
        self.assertIn("401", text)
        self.assertIn("404", text)
        # Strict root-level validation instead of substring matching.
        self.assertIn("check_interaction_response.py", text)
        self.assertNotIn("grep -Eq", text)
        # Token protection and timeouts.
        self.assertIn("non-loopback", text)
        self.assertIn("--max-redirs 0", text)
        self.assertIn("--connect-timeout", text)
        self.assertIn("--max-time", text)
        self.assertIn("umask 077", text)
        self.assertIn("trap ", text)
        # Timeouts must fail explicitly, not be swallowed by a command
        # substitution subshell (which would hide curl's exit status).
        self.assertIn("request timed out", text)
        self.assertIn('"$TMP_DIR/curl.code"', text)
        self.assertNotIn('code="$(http_request', text)
        # Token must not be passed directly as an --header argument.
        self.assertNotIn('-H "Authorization: Bearer $TOKEN"', text)

    def test_run_and_smoke_check_token_permissions(self):
        for name in ("run_core_interaction.sh", "smoke_interaction.sh"):
            text = (TERMUX_DIR / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("stat -c", text)
                self.assertIn("group/others", text)

    def test_integration_doc_exists(self):
        self.assertTrue(INTEGRATION_DOC.is_file())


if __name__ == "__main__":
    unittest.main()
