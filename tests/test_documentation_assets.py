import json
import re
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FILES = [
    "docs/vision/FUTURE_EXPERIENCE_IDEAS.md",
    "docs/getting-started/INSTALLATION.md",
    "docs/getting-started/CONFIGURATION.md",
    "docs/getting-started/STATE_PERSISTENCE.md",
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

    def test_source_of_truth_policy_is_documented(self):
        guide = REPO_ROOT / "docs" / "device-integration" / "README.md"
        text = guide.read_text(encoding="utf-8")
        self.assertIn(
            "GitHub is the source of truth for implementation, protocols, examples and platform integration guides",
            text,
        )

    def test_documentation_does_not_include_personal_validation_ip(self):
        forbidden = "10.255.108.33"
        for path in _documentation_files():
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                self.assertNotIn(forbidden, path.read_text(encoding="utf-8"))

    def test_markdown_relative_links_resolve(self):
        for path in _documentation_files():
            text = path.read_text(encoding="utf-8")
            for target in _markdown_link_targets(text):
                if _is_external_or_anchor(target):
                    continue
                resolved = (path.parent / target).resolve()
                with self.subTest(path=path.relative_to(REPO_ROOT), target=target):
                    self.assertTrue(resolved.exists(), f"Missing link target: {target}")


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
