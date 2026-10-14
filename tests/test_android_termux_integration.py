"""Guards for the experimental Android/Termux integration assets.

These tests validate the committed, device-independent pieces of the
Android/Termux runbook: the example profile, the token tool, the strict
interaction-response checker and the Termux scripts. They do not touch a device.

Most tests run on any platform. The adversarial destination-validation and
signal-interruption tests exercise the Bash smoke script; they run when a Bash
interpreter is available (Git Bash on Windows, /bin/bash elsewhere) and are
skipped otherwise.
"""

import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
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
SMOKE = TERMUX_DIR / "smoke_interaction.sh"
INTEGRATION_DOC = (
    REPO_ROOT / "docs" / "integration" / "ANDROID_TERMUX_MACRODROID.md"
)
DEFAULT_TEST_TOKEN = "integration-token-0123456789abcdef"


def _find_bash():
    """Locate a usable Bash, preferring Git Bash over the WSL launcher."""
    candidates = []
    override = os.environ.get("JARVISOS_BASH")
    if override:
        candidates.append(override)
    which = shutil.which("bash")
    if which and not which.lower().endswith("system32\\bash.exe"):
        candidates.append(which)
    candidates += [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        "/bin/bash",
        "/usr/bin/bash",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


BASH = _find_bash()


def _posix(path):
    """Return a POSIX path for MSYS/Git Bash when running on Windows."""
    text = str(path)
    if os.name == "nt" and len(text) >= 2 and text[1] == ":":
        drive = text[0].lower()
        return "/" + drive + text[2:].replace("\\", "/")
    return text


def _write_token(path, token=DEFAULT_TEST_TOKEN):
    path.write_text(token, encoding="ascii")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


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
            "--expect-success",
            "true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_nested_false_with_root_true(self):
        # A nested false must not mask a root true.
        result = self._run(
            '{"decision": {"commands_executed": false}, "commands_executed": true}'
        )
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_root_true(self):
        result = self._run(
            '{"type": "conversation", "success": true, "commands_executed": true}'
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

    def test_rejects_duplicate_root_key_even_if_last_is_false(self):
        result = self._run('{"commands_executed": true, "commands_executed": false}')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr.lower())

    def test_rejects_duplicate_nested_key(self):
        result = self._run(
            '{"commands_executed": false, "decision": {"a": 1, "a": 2}}'
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr.lower())

    def test_rejects_duplicate_nested_commands_executed(self):
        result = self._run(
            '{"commands_executed": false, '
            '"decision": {"commands_executed": false, "commands_executed": false}}'
        )
        self.assertNotEqual(result.returncode, 0)

    def test_accepts_unique_keys_with_nested_commands_executed(self):
        # Unique nested keys are fine: only the root value is authoritative.
        # (The full conversation contract applies only with --type conversation.)
        result = self._run(
            '{"type": "conversation", "success": true, "commands_executed": false, '
            '"decision": {"commands_executed": false}}',
            "--expect-success",
            "true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class ConversationContractTests(unittest.TestCase):
    """Adversarial checks for the documented greeting contract (docs/api/ROUTES.md)."""

    BASE = {
        "schema_version": 1,
        "type": "conversation",
        "response_text": "Hola. ¿En qué puedo ayudarte?",
        "commands_executed": False,
        "decision": None,
        "success": True,
        "error": None,
    }

    def _run(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "response.json"
            target.write_text(text, encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(CHECKER), "--file", str(target),
                 "--type", "conversation", "--expect-success", "true"],
                capture_output=True,
                text=True,
            )

    def _payload(self, **overrides):
        data = dict(self.BASE)
        data.update(overrides)
        return data

    def _payload_without(self, *keys):
        data = dict(self.BASE)
        for key in keys:
            data.pop(key, None)
        return data

    def test_accepts_documented_contract(self):
        result = self._run(self.BASE)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_missing_schema_version(self):
        result = self._run(self._payload_without("schema_version"))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_schema_version_boolean_true(self):
        # bool is an int subclass: `true` must not satisfy the integer 1.
        result = self._run(self._payload(schema_version=True))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_schema_version_float(self):
        result = self._run(self._payload(schema_version=1.0))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_schema_version_other_int(self):
        result = self._run(self._payload(schema_version=2))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_success_false(self):
        result = self._run(self._payload(success=False))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_success_string(self):
        result = self._run(self._payload(success="true"))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_commands_executed_true(self):
        result = self._run(self._payload(commands_executed=True))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_wrong_type(self):
        result = self._run(self._payload(type="understanding"))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_decision_non_null(self):
        result = self._run(self._payload(decision={"commands_executed": False}))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_decision_missing(self):
        result = self._run(self._payload_without("decision"))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_error_non_null(self):
        result = self._run(self._payload(error="api_request_invalid"))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_error_missing(self):
        result = self._run(self._payload_without("error"))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_empty_response_text(self):
        result = self._run(self._payload(response_text=""))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_missing_response_text(self):
        result = self._run(self._payload_without("response_text"))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_non_string_response_text(self):
        result = self._run(self._payload(response_text=123))
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_duplicate_keys_even_with_valid_values(self):
        raw = (
            '{"schema_version":1,"type":"conversation","response_text":"Hola",'
            '"commands_executed":false,"decision":null,"success":true,'
            '"error":null,"error":null}'
        )
        result = self._run(raw)
        self.assertNotEqual(result.returncode, 0)


class SimulatedServerValidationTests(unittest.TestCase):
    def _capture_via_server(self, body):
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
                return response.read()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def _check(self, body):
        captured = self._capture_via_server(body)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "captured.json"
            target.write_bytes(captured)
            return subprocess.run(
                [sys.executable, str(CHECKER), "--file", str(target),
                 "--type", "conversation", "--expect-success", "true"],
                capture_output=True,
                text=True,
            )

    def test_checker_rejects_crafted_server_response(self):
        body = (
            b'{"type":"conversation","success":true,'
            b'"decision":{"commands_executed":false},'
            b'"commands_executed":true}'
        )
        self.assertNotEqual(self._check(body).returncode, 0)

    def test_checker_rejects_contradictory_greeting_from_server(self):
        # Everything looks like a valid greeting except schema_version is `true`,
        # which the previous checker accepted and the contract forbids.
        body = (
            b'{"schema_version":true,"type":"conversation",'
            b'"response_text":"Hola","commands_executed":false,'
            b'"decision":null,"success":true,"error":null}'
        )
        self.assertNotEqual(self._check(body).returncode, 0)


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

    def test_smoke_validates_destination_structurally(self):
        text = SMOKE.read_text(encoding="utf-8")
        self.assertIn("validate_base", text)
        self.assertIn("unsafe JARVISOS_BASE", text)
        # Validation must run before the Authorization file is built.
        self.assertLess(text.index("if ! validate_base"), text.index("AUTH_CONF="))

    def test_smoke_hardens_curl_against_env_and_redirects(self):
        text = SMOKE.read_text(encoding="utf-8")
        self.assertIn("curl -q -sS", text)  # -q ignores ~/.curlrc
        self.assertIn("--noproxy '*'", text)
        self.assertIn("--max-redirs 0", text)
        self.assertIn("--proto '=http'", text)
        self.assertIn("--connect-timeout", text)
        self.assertIn("--max-time", text)
        self.assertIn("request timed out", text)
        self.assertIn('"$TMP_DIR/curl.code"', text)
        self.assertNotIn('code="$(http_request', text)

    def test_smoke_handles_interruption(self):
        text = SMOKE.read_text(encoding="utf-8")
        self.assertIn("trap 'on_signal; exit 130' INT", text)
        self.assertIn("trap 'on_signal; exit 143' TERM", text)
        self.assertIn("umask 077", text)
        self.assertIn("trap cleanup EXIT", text)
        self.assertIn('kill "$CURL_PID"', text)

    def test_smoke_uses_strict_checker_and_keeps_token_out_of_argv(self):
        text = SMOKE.read_text(encoding="utf-8")
        self.assertIn("/api/v1/interactions", text)
        self.assertIn("/api/v1/commands", text)
        self.assertIn("401", text)
        self.assertIn("404", text)
        self.assertIn("check_interaction_response.py", text)
        self.assertNotIn("grep -Eq", text)
        self.assertNotIn('-H "Authorization: Bearer $TOKEN"', text)

    def test_run_and_smoke_check_token_permissions(self):
        for name in ("run_core_interaction.sh", "smoke_interaction.sh"):
            text = (TERMUX_DIR / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("stat -c", text)
                self.assertIn("group/others", text)

    def test_integration_doc_exists(self):
        self.assertTrue(INTEGRATION_DOC.is_file())


class SmokeBaseValidationTests(unittest.TestCase):
    ADVERSARIAL = [
        "http://127.0.0.1:80@evil.com:9999",
        "http://127.0.0.1:80@127.0.0.1:8765",
        "http://127.0.0.1:8765@evil.com",
        "http://user:pass@127.0.0.1:8765",
        "http://user@127.0.0.1:8765",
        "http://evil.com:8765",
        "https://127.0.0.1:8765",
        "http://127.0.0.1:8765/",
        "http://127.0.0.1:8765/api/v1/interactions",
        "http://127.0.0.1:8765?x=1",
        "http://127.0.0.1:8765#frag",
        "http://127.0.0.1:99999",
        "http://127.0.0.1:0",
        "http://127.0.0.1:abcdef",
        "http://127.0.0.1:8765 ",
        " http://127.0.0.1:8765",
        "http://127.0.0.1.evil.com",
        "http://localhost.evil.com",
        "HTTP://127.0.0.1:8765",
        r"http://127.0.0.1\@evil.com:8765",
        "ftp://127.0.0.1",
        "http://[::1]:8765",
    ]
    VALID = [
        "http://127.0.0.1",
        "http://127.0.0.1:8765",
        "http://localhost",
        "http://localhost:8765",
    ]

    def setUp(self):
        if BASH is None:
            self.skipTest("bash not available")

    def _run_smoke(self, base):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "interaction.token"
            _write_token(token)
            env = dict(os.environ)
            env.update(
                {
                    "JARVISOS_BASE": base,
                    "JARVISOS_TOKEN_FILE": _posix(token),
                    "JARVISOS_CONNECT_TIMEOUT": "2",
                    "JARVISOS_MAX_TIME": "2",
                }
            )
            return subprocess.run(
                [BASH, str(SMOKE)],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )

    def test_adversarial_bases_are_refused_before_any_request(self):
        for base in self.ADVERSARIAL:
            with self.subTest(base=base):
                result = self._run_smoke(base)
                self.assertNotEqual(
                    result.returncode, 0, result.stdout + result.stderr
                )
                self.assertIn("unsafe JARVISOS_BASE", result.stderr)
                # The request phase was never reached.
                self.assertNotIn("== 1. health ==", result.stdout)

    def test_valid_loopback_bases_pass_validation(self):
        for base in self.VALID:
            with self.subTest(base=base):
                result = self._run_smoke(base)
                self.assertNotIn("unsafe JARVISOS_BASE", result.stderr)
                # Validation accepted the base, so the request phase started.
                self.assertIn("== 1. health ==", result.stdout)


class _HangingServer:
    """Accepts connections and never responds, counting them."""

    def __init__(self):
        self._listener = socket.socket()
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self.port = self._listener.getsockname()[1]
        self.accepted = 0
        self._held = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        self._listener.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.accepted += 1
            self._held.append(conn)

    def close(self):
        self._stop.set()
        self._listener.close()
        self._thread.join(timeout=2)
        for conn in self._held:
            try:
                conn.close()
            except OSError:
                pass


class SmokeInterruptionTests(unittest.TestCase):
    def setUp(self):
        if BASH is None:
            self.skipTest("bash not available")

    def test_signal_during_slow_request_stops_and_cleans_up(self):
        server = _HangingServer()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                token = root / "interaction.token"
                _write_token(token)
                tmpdir = root / "tmproot"
                tmpdir.mkdir()
                env = dict(os.environ)
                env.update(
                    {
                        "JARVISOS_BASE": f"http://127.0.0.1:{server.port}",
                        "JARVISOS_TOKEN_FILE": _posix(token),
                        "TMPDIR": _posix(tmpdir),
                        "JARVISOS_CONNECT_TIMEOUT": "2",
                        "JARVISOS_MAX_TIME": "15",
                    }
                )
                wrapper = (
                    "bash tools/termux/smoke_interaction.sh & p=$!; "
                    "sleep 1; kill -TERM \"$p\" 2>/dev/null; "
                    "wait \"$p\"; echo \"SMOKE_RC=$?\""
                )
                started = time.time()
                try:
                    result = subprocess.run(
                        [BASH, "-c", wrapper],
                        cwd=str(REPO_ROOT),
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=25,
                    )
                except subprocess.TimeoutExpired:
                    self.fail("smoke did not stop after the signal")
                elapsed = time.time() - started

                combined = result.stdout + result.stderr
                self.assertIn("SMOKE_RC=", result.stdout, combined)
                code = int(result.stdout.strip().split("SMOKE_RC=")[-1])
                self.assertNotEqual(code, 0, combined)
                self.assertNotEqual(code, 28, "expected interruption, not timeout")
                self.assertLess(elapsed, 10, combined)
                # No further requests were issued after the interruption.
                self.assertEqual(server.accepted, 1, combined)
                # Temporary files were cleaned up on interruption.
                self.assertEqual(list(tmpdir.iterdir()), [], combined)
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
