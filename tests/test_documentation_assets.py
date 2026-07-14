import json
import re
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FILES = [
    "AGENTS.md",
    "docs/vision/FUTURE_EXPERIENCE_IDEAS.md",
    "docs/project/PROJECT_STATE.md",
    "docs/ai/README.md",
    "docs/ai/STRUCTURED_PLAN.md",
    "docs/ai/SAFE_CONTEXT.md",
    "docs/ai/FAKE_AI_ADAPTER.md",
    "docs/getting-started/INSTALLATION.md",
    "docs/getting-started/CONFIGURATION.md",
    "docs/getting-started/STATE_PERSISTENCE.md",
    "docs/getting-started/HTTP_PROFILE_VALIDATION.md",
    "docs/getting-started/FIRST_RUN.md",
    "docs/getting-started/FIRST_DEVICE.md",
    "docs/device-integration/README.md",
    "docs/device-integration/DEVICE_PROTOCOL.md",
    "docs/device-integration/CAPABILITY_MODEL.md",
    "docs/device-integration/DRIVER_DEVELOPMENT.md",
    "docs/device-integration/SECURITY_GUIDELINES.md",
    "docs/device-integration/TROUBLESHOOTING.md",
    "docs/platforms/README.md",
    "docs/platforms/ESP32_ESP_IDF.md",
    "docs/platforms/ESP32_ARDUINO.md",
    "docs/platforms/ESP8266.md",
    "docs/platforms/ARDUINO.md",
    "docs/platforms/STM32.md",
    "docs/platforms/RASPBERRY_PI.md",
    "docs/platforms/LINUX_PC.md",
    "docs/platforms/WINDOWS_PC.md",
    "docs/platforms/ANDROID.md",
    "docs/examples/README.md",
    "examples/http-led/README.md",
    "examples/http-led/protocol-examples/apply-on.json",
    "examples/http-led/protocol-examples/apply-off.json",
    "examples/http-led/protocol-examples/read-status.json",
    "examples/http-led/protocol-examples/success-on.json",
    "examples/http-led/protocol-examples/success-off.json",
    "examples/http-led/protocol-examples/error-operation-not-supported.json",
    "profiles/http-lab.example.json",
    "examples/http-led/esp32-idf/CMakeLists.txt",
    "examples/http-led/esp32-idf/README.md",
    "examples/http-led/esp32-idf/main/CMakeLists.txt",
    "examples/http-led/esp32-idf/main/Kconfig.projbuild",
    "examples/http-led/esp32-idf/main/jarvis_http_led_main.c",
]


class DocumentationAssetsTests(unittest.TestCase):
    def test_required_documentation_files_exist(self):
        for relative_path in REQUIRED_FILES:
            with self.subTest(path=relative_path):
                self.assertTrue((REPO_ROOT / relative_path).is_file())

    def test_protocol_examples_are_valid_json(self):
        examples_dir = REPO_ROOT / "examples" / "http-led" / "protocol-examples"
        for path in examples_dir.glob("*.json"):
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)

    def test_example_profile_is_valid_json(self):
        profile = REPO_ROOT / "profiles" / "http-lab.example.json"
        payload = json.loads(profile.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["profile"], "http-lab")
        self.assertEqual(
            payload["runtime_options"]["state_store_path"],
            "../state/http-lab.state.json",
        )

    def test_local_profiles_are_gitignored(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("profiles/*.local.json", gitignore)

    def test_source_of_truth_policy_is_documented(self):
        guide = REPO_ROOT / "docs" / "device-integration" / "README.md"
        text = guide.read_text(encoding="utf-8")
        self.assertIn(
            "GitHub is the source of truth for implementation, protocols, examples and platform integration guides",
            text,
        )

    def test_agent_context_documents_link_each_other(self):
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        project_state = (
            REPO_ROOT / "docs" / "project" / "PROJECT_STATE.md"
        ).read_text(encoding="utf-8")

        self.assertIn("docs/project/PROJECT_STATE.md", agents)
        self.assertIn("../../AGENTS.md", project_state)
        self.assertIn("GitHub is the source of truth", agents)
        self.assertIn("Notion is the source of truth", project_state)

    def test_project_state_documents_current_epic_boundary(self):
        project_state = (
            REPO_ROOT / "docs" / "project" / "PROJECT_STATE.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Epics 1-9 are completed", project_state)
        self.assertIn("Epic 10 is in progress", project_state)
        self.assertIn("Phase 10.3 is in implementation pending merge", project_state)
        self.assertIn("c3a6f78a72b9c08db550743cec6910934c44899d", project_state)
        self.assertIn("Default runtime remains empty, simulated, and offline-safe", project_state)

    def test_ai_documentation_states_fake_only_boundary(self):
        ai_readme = (REPO_ROOT / "docs" / "ai" / "README.md").read_text(
            encoding="utf-8"
        )
        fake_adapter = (REPO_ROOT / "docs" / "ai" / "FAKE_AI_ADAPTER.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Deterministic Fake Only", ai_readme)
        self.assertIn("no network", fake_adapter)
        self.assertIn("no credentials", fake_adapter)
        self.assertIn("not registered in the default runtime", fake_adapter)

    def test_documentation_does_not_include_personal_validation_ip(self):
        forbidden = "10.255.108.33"
        for path in _documentation_files():
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                self.assertNotIn(forbidden, path.read_text(encoding="utf-8"))

    def test_documentation_does_not_include_wifi_credentials(self):
        forbidden = ["ssid=", "password=", "wifi_password"]
        for path in _documentation_files():
            text = path.read_text(encoding="utf-8").lower()
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                for token in forbidden:
                    self.assertNotIn(token, text)

    def test_markdown_relative_links_resolve(self):
        for path in _documentation_files():
            text = path.read_text(encoding="utf-8")
            for target in _markdown_link_targets(text):
                if _is_external_or_anchor(target):
                    continue
                resolved = (path.parent / target).resolve()
                with self.subTest(path=path.relative_to(REPO_ROOT), target=target):
                    self.assertTrue(resolved.exists(), f"Missing link target: {target}")

    def test_http_led_docs_prefer_profile_based_runtime(self):
        docs = [
            REPO_ROOT / "docs" / "getting-started" / "FIRST_DEVICE.md",
            REPO_ROOT / "docs" / "platforms" / "ESP32_ESP_IDF.md",
            REPO_ROOT / "examples" / "http-led" / "README.md",
        ]
        profile_command = "python -m jarvis_core --config profiles/http-lab.local.json"
        manual_command = "python tools/run_http_led_validation.py"

        for path in docs:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                self.assertIn(profile_command, text)
                self.assertIn(manual_command, text)
                self.assertLess(text.index(profile_command), text.index(manual_command))

    def test_http_profile_validation_documents_epic9_runtime_boundaries(self):
        guide = REPO_ROOT / "docs" / "getting-started" / "HTTP_PROFILE_VALIDATION.md"
        text = guide.read_text(encoding="utf-8")

        self.assertIn("python -m jarvis_core --config profiles/http-lab.local.json", text)
        self.assertIn("Hardware validation is manual", text)
        self.assertIn("CI uses a fake HTTP transport", text)
        self.assertIn("Restored state is last-known semantic state", text)
        self.assertIn("No retries are implemented", text)


def _documentation_files():
    for base in (REPO_ROOT / "docs", REPO_ROOT / "examples" / "http-led"):
        yield from base.rglob("*.md")


def _markdown_link_targets(text):
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = match.group(1).split("#", 1)[0]
        if target:
            yield target


def _is_external_or_anchor(target):
    return (
        target.startswith("http://")
        or target.startswith("https://")
        or target.startswith("mailto:")
        or target.startswith("#")
    )


if __name__ == "__main__":
    unittest.main()
