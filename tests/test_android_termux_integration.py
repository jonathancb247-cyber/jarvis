"""Guards for the experimental Android/Termux integration assets.

These tests validate the committed, device-independent pieces of the
Android/Termux runbook: the example profile, the token tool and the Termux
scripts. They do not touch a device, do not start a server and do not require
network access.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jarvis_core.bootstrap import build_runtime_from_config
from jarvis_core.configuration import RuntimeConfigurationLoader


REPO_ROOT = Path(__file__).resolve().parents[1]
TERMUX_DIR = REPO_ROOT / "tools" / "termux"
PROFILE_PATH = REPO_ROOT / "profiles" / "android-termux.example.json"
TOKEN_SCRIPT = TERMUX_DIR / "make_interaction_token.py"
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


class AndroidTermuxTokenToolTests(unittest.TestCase):
    def _run(self, *arguments):
        return subprocess.run(
            [sys.executable, str(TOKEN_SCRIPT), *arguments],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_writes_valid_token_without_printing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "interaction.token"
            result = self._run("--path", str(target))
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


class AndroidTermuxScriptTests(unittest.TestCase):
    def test_termux_scripts_exist(self):
        for name in (
            "bootstrap_termux.sh",
            "run_core_interaction.sh",
            "smoke_interaction.sh",
        ):
            with self.subTest(name=name):
                self.assertTrue((TERMUX_DIR / name).is_file())

    def test_core_runner_is_interaction_only_and_reads_token_from_file(self):
        text = (TERMUX_DIR / "run_core_interaction.sh").read_text(encoding="utf-8")
        self.assertIn("--interaction-only", text)
        self.assertIn("JARVIS_API_INTERACTION_TOKEN", text)
        self.assertIn('"$TOKEN_FILE"', text)
        self.assertIn("127.0.0.1", text)

    def test_smoke_script_checks_auth_and_disabled_command_route(self):
        text = (TERMUX_DIR / "smoke_interaction.sh").read_text(encoding="utf-8")
        self.assertIn("/api/v1/interactions", text)
        self.assertIn("/api/v1/commands", text)
        self.assertIn("commands_executed", text)
        self.assertIn("401", text)
        self.assertIn("404", text)

    def test_integration_doc_exists(self):
        self.assertTrue(INTEGRATION_DOC.is_file())


if __name__ == "__main__":
    unittest.main()
