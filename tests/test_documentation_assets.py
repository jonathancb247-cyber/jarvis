import json
import re
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FILES = [
    "AGENTS.md",
    "docs/vision/FUTURE_EXPERIENCE_IDEAS.md",
    "docs/project/PROJECT_STATE.md",
    "docs/api/README.md",
    "docs/api/ROUTES.md",
    "docs/api/SECURITY.md",
    "docs/dashboard/README.md",
    "docs/dashboard/USAGE.md",
    "docs/dashboard/SECURITY.md",
    "docs/dashboard/HARDWARE_VALIDATION.md",
    "docs/design/VOICE_BENCHMARK.md",
    "docs/design/VOICE_PROVIDER_BAKEOFF.md",
    "docs/design/AI_PROVIDER_STRATEGY.md",
    "docs/design/SECOND_BRAIN_MEMORY_BOUNDARY.md",
    "docs/design/SECOND_BRAIN_STORAGE_PERSISTENCE_BOUNDARY.md",
    "docs/design/JUDGMENT_AUTONOMY_BOUNDARY.md",
    "docs/design/LEARNING_ADAPTIVE_PATTERN_BOUNDARY.md",
    "docs/design/CONTEXT_ENGINE_BOUNDARY.md",
    "docs/design/ATTENTION_PROACTIVITY_BOUNDARY.md",
    "docs/design/COGNITIVE_SIGNAL_EVIDENCE_VOCABULARY.md",
    "docs/design/WEARABLE_BOUNDARY.md",
    "docs/drivers/MQTT_DRIVER.md",
    "docs/drivers/MQTT_VALIDATION.md",
    "docs/ai/README.md",
    "docs/ai/STRUCTURED_PLAN.md",
    "docs/ai/SAFE_CONTEXT.md",
    "docs/ai/FAKE_AI_ADAPTER.md",
    "docs/ai/GEMINI_PROVIDER.md",
    "docs/ai/GEMINI_VALIDATION.md",
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
    "profiles/mqtt-lab.example.json",
    "tools/mosquitto-loopback.conf",
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
        self.assertIn("Phase 10.3 is completed", project_state)
        self.assertIn("Phase 10.9 is completed", project_state)
        self.assertIn("Gemini is Current / Experimental", project_state)
        self.assertIn("Gemini real provider validated", project_state)
        self.assertIn("Phase 10.10 is blocked", project_state)
        self.assertIn("Phase 12.1 is completed as design", project_state)
        self.assertIn("Phase 12.2 is completed", project_state)
        self.assertIn("Phase 12.2 - MQTT Request/Response Driver Minimal Implementation is completed", project_state)
        self.assertIn("MQTT Driver is Current / Experimental", project_state)
        self.assertIn("Phase 12.3 is completed", project_state)
        self.assertIn("Phase 12.3 - Local Mosquitto Integration Validation is completed", project_state)
        self.assertIn("real local loopback Mosquitto validation was completed", project_state)
        self.assertIn("validating a real loopback Mosquitto broker", project_state)
        self.assertIn("Phase 12.4 is blocked", project_state)
        self.assertIn("Cognitive Phase 1 is completed", project_state)
        self.assertIn("Deterministic Cognitive Vertical Slice merged in PR #58", project_state)
        self.assertIn("bc92c31992544f6d3824a7a1a39666b405977b23", project_state)
        self.assertIn("Cognitive Phase 1 validation: 609 tests passing", project_state)
        self.assertIn("scripted evidence -> Context -> Learning plus seeded read-only Memory -> Judgment -> Attention -> deterministic report", project_state)
        self.assertIn("Deep Focus, Night Mode Suggestion, Stale Device, Explicit User Correction, Private Notification and Habit Proposal", project_state)
        self.assertIn("recommendation/report-only", project_state)
        self.assertIn("learned patterns do not automatically create Memory, Rules or Delegation", project_state)
        self.assertIn("no execution authority", project_state)
        self.assertIn("no Runtime, Planner, Driver, DeviceState, API, Dashboard, AI, Voice, persistence, network, provider, hardware, microphone/speaker or notification-delivery path", project_state)
        self.assertIn("Cognitive Phase 2 is completed", project_state)
        self.assertIn("Local Cognitive Report Surface merged in PR #60", project_state)
        self.assertIn("9f2da69e0c8b9130bde13757d82982f5f8a1d56c", project_state)
        self.assertIn("Cognitive Phase 2 validation: 617 tests passing", project_state)
        self.assertIn("python -m jarvis_core.cognitive", project_state)
        self.assertIn("python -m jarvis_core.cognitive --format json", project_state)
        self.assertIn("Cognitive Phase 2 text and JSON output are deterministic", project_state)
        self.assertIn("Cognitive Phase 2 has no Runtime/Planner/Driver path", project_state)
        self.assertIn("no Runtime, Planner, Driver, DeviceState, API, Dashboard, Voice, AI/provider, persistence, network, hardware, notification delivery, policy, confirmation or delegated autonomy path", project_state)
        self.assertIn("Cognitive Phase 3 is completed", project_state)
        self.assertIn("Read-Only DeviceState Cognitive Signal Mapping merged in PR #62", project_state)
        self.assertIn("be319286fa50fbc88df141995627d50d3b829ce3", project_state)
        self.assertIn("d6695cd226718d8880ae9d4e88b16b6656f146b5", project_state)
        self.assertIn("Cognitive Phase 3 validation: 629 tests passing", project_state)
        self.assertIn("first real JarvisOS semantic boundary entered cognition as evidence", project_state)
        self.assertIn("DeviceState semantic input into cognitive evidence; no live DeviceState object enters cognition", project_state)
        self.assertIn("known/current -> fresh cognitive evidence", project_state)
        self.assertIn("known/not-current -> conservatively stale", project_state)
        self.assertIn("unknown -> insufficient low-confidence evidence with no fabricated properties", project_state)
        self.assertIn("safe semantic properties bounded, immutable and filtered", project_state)
        self.assertIn("stale evidence produces read/clarify recommendation only", project_state)
        self.assertIn("no explicit read occurs", project_state)
        self.assertIn("cognition treats DeviceState only as evidence", project_state)
        self.assertIn("Wearable Phase 1 is completed", project_state)
        self.assertIn("Wear OS Presence / Connection Signal merged in PR #66", project_state)
        self.assertIn("9621d4197ed1cf2ca00d4be7bc791cfd6a19a9e3", project_state)
        self.assertIn("Wearable Phase 1 validation: 642 tests passing", project_state)
        self.assertIn("connected, disconnected, unknown and stale", project_state)
        self.assertIn("detached, frozen and read-only `WearablePresenceProjection`", project_state)
        self.assertIn("fake fixtures map into cognitive evidence only", project_state)
        self.assertIn("existing six-scenario cognitive report remains unchanged", project_state)
        self.assertIn("`watch_connected` means only that a known wearable probe appears connected", project_state)
        self.assertIn("does not imply user presence, watch wearing, awake state, user availability, identity/authentication, health or location", project_state)
        self.assertIn("Degraded wearable states reduce wearable evidence only", project_state)
        self.assertIn("no real Pixel Watch connectivity", project_state)
        self.assertIn("Sensitive Wearable Context remains blocked", project_state)
        self.assertIn("Real Pixel Watch validation remains a separate future hardware gate", project_state)
        self.assertIn("Second Brain Phase 1 is completed", project_state)
        self.assertIn("Deterministic In-Memory Knowledge Retrieval merged in PR #69", project_state)
        self.assertIn("fbb64eac19f8f880794322ac647ac8040ba069b2", project_state)
        self.assertIn("Second Brain Phase 1 validation: 656 tests passing", project_state)
        self.assertIn("seeded approved knowledge", project_state)
        self.assertIn("exact and normalized keyword-topic matching", project_state)
        self.assertIn("current, stale, historical, superseded and contradicted freshness", project_state)
        self.assertIn("superseded evidence is retained but not treated as co-current", project_state)
        self.assertIn("explicit correction outranks prior fact", project_state)
        self.assertIn("equal-strength contradictions return contradicted rather than fabricated truth", project_state)
        self.assertIn("unknown queries return no fabricated answer", project_state)
        self.assertIn("deterministic text and JSON diagnostic output", project_state)
        self.assertIn("no execution authority", project_state)
        self.assertIn("real Pixel Watch hardware validation remains separate/pending", project_state)
        self.assertIn("without claiming physical ESP32 MQTT validation complete", project_state)
        self.assertIn("Second Brain Phase 1 does not implement persistence", project_state)
        self.assertIn("Notion/GitHub/Obsidian/Google Drive connectors", project_state)
        self.assertIn("embeddings, vector DB, semantic retrieval, RAG", project_state)
        self.assertIn("Second Brain Phase 2 is completed", project_state)
        self.assertIn("SQLite Fixture Persistence merged in PR #72", project_state)
        self.assertIn("f7c0f5e870c4c53886221264aa33bc2aee91c3df", project_state)
        self.assertIn("Second Brain Phase 2 validation: 675 tests passing", project_state)
        self.assertIn("Python stdlib `sqlite3`", project_state)
        self.assertIn("SQLite is a storage adapter and not a core JarvisOS dependency", project_state)
        self.assertIn("Second Brain remains in-memory by default", project_state)
        self.assertIn("--storage sqlite --db PATH", project_state)
        self.assertIn("schema version 1", project_state)
        self.assertIn("duplicate ID rejection", project_state)
        self.assertIn("explicit correction/supersession transactions", project_state)
        self.assertIn("logical delete", project_state)
        self.assertIn("hard purge", project_state)
        self.assertIn("`user_scope` filtering/isolation", project_state)
        self.assertIn("bounded `storage_corrupt`", project_state)
        self.assertIn("`schema_version_unsupported`", project_state)
        self.assertIn("SQLite restart/correction/purge persistence proofs passed", project_state)
        self.assertIn("synthetic fixture data survives process restart", project_state)
        self.assertIn("hard-purged records remain absent after restart", project_state)
        self.assertIn("jarvis_core/second_brain/repository.py", project_state)
        self.assertIn("tests/test_second_brain_sqlite_repository.py", project_state)
        self.assertIn("PERSONAL, SENSITIVE and RESTRICTED durable data remain blocked", project_state)
        self.assertIn("fixture-only keyword guards are not a future real-memory safety model", project_state)
        self.assertIn("State Store DeviceState-only", project_state)
        self.assertIn("SQLite does not become Runtime, DeviceState or State Store persistence", project_state)
        self.assertIn("Second Brain Phase 3 remains unopened", project_state)
        self.assertIn("Real personal memory requires a separate Sensitive Memory / Retention / encryption gate", project_state)
        self.assertIn("AI-backed memory writes", project_state)
        self.assertNotIn("Second Brain Phase 2 remains unopened", project_state)
        self.assertNotIn("persistent Second Brain storage;", project_state)
        self.assertNotIn("SQLite-backed memory;", project_state)
        self.assertIn("cognitive DeviceState mutation or device refresh", project_state)
        self.assertIn("real wearable integration beyond fake deterministic presence evidence", project_state)
        self.assertIn("real Pixel Watch connectivity or Wear OS app/probe", project_state)
        self.assertIn("Android/ADB wearable integration", project_state)
        self.assertIn("HR, HRV, sleep, activity/exercise, precise location, biometrics or wrist presence as identity", project_state)
        self.assertIn("cognitive background polling or automatic scene activation", project_state)
        self.assertNotIn("real MQTT broker validation;", project_state)
        self.assertNotIn("Phase 12.3 is pending merge", project_state)
        self.assertNotIn("local loopback Mosquitto validation is pending merge", project_state)
        self.assertNotIn("Phase 12.3 - Local Mosquitto Integration Validation is pending merge", project_state)
        self.assertIn("80e83fc77534e96da74dc440942845f911ae47b4", project_state)
        self.assertIn("871f5f02cdac5f00741534d3f87e2a799d060417", project_state)
        self.assertIn("e374d30f2c28865c82fcb880f7079974ea1dfca4", project_state)
        self.assertIn("c3a6f78a72b9c08db550743cec6910934c44899d", project_state)
        self.assertIn("Default runtime remains empty, simulated, and offline-safe", project_state)
        self.assertNotIn("Phase 10.9 is pending merge/manual validation", project_state)
        self.assertNotIn("no real Gemini call has been made", project_state)
        self.assertNotIn("pending merge/manual Gemini validation", project_state)
        self.assertNotIn("Phase 12.2 is pending merge", project_state)
        self.assertNotIn("Phase 12.2 - MQTT Request/Response Driver Minimal Implementation is pending merge", project_state)

    def test_project_state_documents_runtime_api_boundary(self):
        project_state = (
            REPO_ROOT / "docs" / "project" / "PROJECT_STATE.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Epic 11 is in progress", project_state)
        self.assertIn("Phase 11.1 is completed as design", project_state)
        self.assertIn("Phase 11.2 is completed", project_state)
        self.assertIn("Runtime API is Current / Experimental", project_state)
        self.assertIn("Phase 11.3 is completed", project_state)
        self.assertIn("Dashboard is Current / Experimental", project_state)
        self.assertIn("Phase 11.4 - Profile-based Hardware Dashboard Validation is completed", project_state)
        self.assertIn("ESP32 HTTP Dashboard path physically validated", project_state)
        self.assertIn("physical disconnect plus explicit read produced `stale/not current`", project_state)
        self.assertIn("prior semantic properties preserved", project_state)
        self.assertIn("explicit `status.read` refreshes physical freshness", project_state)
        self.assertIn("Dashboard auto-refresh refreshes projected Runtime API state only", project_state)
        self.assertIn("does not imply hardware polling", project_state)
        self.assertIn("`stale` is not `unavailable`", project_state)
        self.assertNotIn("Phase 11.4 - Profile-based Hardware Dashboard Validation is completed for the PR validation scope and pending merge", project_state)
        self.assertNotIn("hardware Dashboard validation completed for PR scope and pending merge", project_state)
        self.assertIn("Epic 10 remains unchanged", project_state)
        self.assertNotIn("Phase 11.2 is pending merge", project_state)
        self.assertNotIn("Phase 11.3 is pending merge", project_state)

    def test_runtime_api_documentation_states_localhost_boundary(self):
        api_readme = (REPO_ROOT / "docs" / "api" / "README.md").read_text(
            encoding="utf-8"
        )
        api_security = (REPO_ROOT / "docs" / "api" / "SECURITY.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("localhost-only", api_readme)
        self.assertIn("python -m jarvis_core.api --config", api_readme)
        self.assertIn("Dashboard;", api_readme)
        self.assertIn("127.0.0.1", api_security)
        self.assertIn("LAN mode", api_security)

    def test_dashboard_documentation_states_local_only_boundary(self):
        dashboard_readme = (
            REPO_ROOT / "docs" / "dashboard" / "README.md"
        ).read_text(encoding="utf-8")
        dashboard_security = (
            REPO_ROOT / "docs" / "dashboard" / "SECURITY.md"
        ).read_text(encoding="utf-8")

        self.assertIn("python -m jarvis_core.dashboard --config", dashboard_readme)
        self.assertIn("local browser UI", dashboard_readme)
        self.assertIn("AI chat", dashboard_readme)
        self.assertIn("Hardware Validation", dashboard_readme)
        self.assertIn("127.0.0.1", dashboard_security)
        self.assertIn("no external CDN", dashboard_security)

    def test_ai_documentation_states_ai_boundary(self):
        ai_readme = (REPO_ROOT / "docs" / "ai" / "README.md").read_text(
            encoding="utf-8"
        )
        fake_adapter = (REPO_ROOT / "docs" / "ai" / "FAKE_AI_ADAPTER.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("Fake Adapter plus Validated Gemini Provider", ai_readme)
        self.assertIn("real-provider validation with `gemini-3.6-flash`", ai_readme)
        self.assertIn("production-approved AI providers", ai_readme)
        self.assertIn("automatic provider fallback", ai_readme)
        self.assertIn("no network", fake_adapter)
        self.assertIn("no credentials", fake_adapter)
        self.assertIn("not registered in the default runtime", fake_adapter)
        gemini_provider = (
            REPO_ROOT / "docs" / "ai" / "GEMINI_PROVIDER.md"
        ).read_text(encoding="utf-8")
        gemini_validation = (
            REPO_ROOT / "docs" / "ai" / "GEMINI_VALIDATION.md"
        ).read_text(encoding="utf-8")
        self.assertIn("GEMINI_API_KEY", gemini_provider)
        self.assertIn("GEMINI_AI_VALIDATION_REQUIRED", gemini_validation)
        self.assertIn("No Gemini-specific DTO exists", gemini_provider)
        self.assertIn("Experimental / Real-Provider Validated", gemini_provider)
        self.assertIn("Phase 10.9 completed real-provider validation", gemini_provider)
        self.assertIn("permanently selected", gemini_validation)
        self.assertNotIn("Status: Experimental / Not Real-Validated", gemini_provider)
        self.assertNotIn("Phase 10.9 does not perform a real Gemini call", gemini_provider)

    def test_ai_provider_strategy_documents_current_provider_lanes(self):
        ai_readme = (REPO_ROOT / "docs" / "ai" / "README.md").read_text(
            encoding="utf-8"
        )
        strategy = (
            REPO_ROOT / "docs" / "design" / "AI_PROVIDER_STRATEGY.md"
        ).read_text(encoding="utf-8")

        self.assertIn("../design/AI_PROVIDER_STRATEGY.md", ai_readme)
        self.assertIn("Structured Planning Provider", strategy)
        self.assertIn("Local Essential AI", strategy)
        self.assertIn("Voice / STT / Realtime Provider Lane", strategy)
        self.assertIn("PR #38 classification: REFERENCE / REDESIGN.", strategy)
        self.assertIn(
            "PR #39 classification: RESEARCH / DO NOT MERGE AS VALIDATED PROVIDER.",
            strategy,
        )
        self.assertIn("provider registry", strategy)
        self.assertIn("automatic provider fallback", strategy)
        self.assertIn("no DeviceState mutation", strategy)

    def test_cognitive_architecture_adrs_are_design_only(self):
        expected = {
            "SECOND_BRAIN_MEMORY_BOUNDARY.md": [
                "Memory is not execution authority.",
                "State Store must not become Second Brain storage.",
                "Silent persistent memory is not approved.",
            ],
            "SECOND_BRAIN_STORAGE_PERSISTENCE_BOUNDARY.md": [
                "Persistence stores approved knowledge.",
                "SQLite is a storage adapter choice, not a core JarvisOS dependency.",
                "`JsonDeviceStateStore` remains DeviceState-only.",
                "No AI provider may commit durable memory directly.",
                "Second Brain storage\n-> Runtime action",
            ],
            "JUDGMENT_AUTONOMY_BOUNDARY.md": [
                "Judgment is not authority.",
                "Level 4 - Autonomous: rejected.",
                "Judgment must never",
            ],
            "LEARNING_ADAPTIVE_PATTERN_BOUNDARY.md": [
                "Learning produces evidence and hypotheses, not authority.",
                "Learning must never create delegation automatically.",
                "silently profile users",
            ],
            "CONTEXT_ENGINE_BOUNDARY.md": [
                "What appears to be happening now?",
                "Context does not answer",
                "activate scenes automatically",
            ],
            "ATTENTION_PROACTIVITY_BOUNDARY.md": [
                "Should Jarvis interrupt or surface this now, and how?",
                "There is no Attention -> Runtime path.",
                "must not optimize for engagement",
            ],
            "COGNITIVE_SIGNAL_EVIDENCE_VOCABULARY.md": [
                "Shared vocabulary is not shared cognitive state.",
                "fuzzy membership is not confidence",
                "Reject a universal `CognitiveEvidence` base model",
            ],
        }

        for filename, required_text in expected.items():
            path = REPO_ROOT / "docs" / "design" / filename
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=filename):
                self.assertIn("Status: Accepted / Design - Not Implemented", text)
                self.assertIn("Future Implementation Direction", text)
                for phrase in required_text:
                    self.assertIn(phrase, text)

    def test_second_brain_storage_persistence_adr_is_design_only(self):
        text = (
            REPO_ROOT
            / "docs"
            / "design"
            / "SECOND_BRAIN_STORAGE_PERSISTENCE_BOUNDARY.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Status: Accepted / Design - Not Implemented", text)
        self.assertIn("SQLite", text)
        self.assertIn("Python's standard-library `sqlite3`", text)
        self.assertIn("fixture-only validation", text)
        self.assertIn("State Store", text)
        self.assertIn("It must not become Second Brain", text)
        self.assertIn("schema versioning", text)
        self.assertIn("no silent durable writes", text)
        self.assertIn("explicit \"remember X\" request", text)
        self.assertIn("explicit correction", text)
        self.assertIn("user-approved save suggestion", text)
        self.assertIn("Not automatically eligible", text)
        self.assertIn("raw conversation history", text)
        self.assertIn("AI or provider guesses", text)
        self.assertIn("credentials or secrets", text)
        self.assertIn("correction and supersession must be atomic", text)
        self.assertIn("\"Forget this\" must not merely hide content", text)
        self.assertIn("hard purge", text)
        self.assertIn("restricted / never-store", text)
        self.assertIn("Sensitive Memory remains a future gate", text)
        self.assertIn("no cross-user recall", text)
        self.assertIn("unknown identity cannot access personal durable memory", text)
        self.assertIn("current GitHub/Notion truth", text)
        self.assertIn("stale cached memory snapshot", text)
        self.assertIn("KnowledgeRepository", text)
        self.assertIn("SQLiteKnowledgeRepository", text)
        self.assertIn("Phase 1 retrieval parity", text)
        self.assertIn("SQLite alone is not a security boundary", text)
        self.assertIn("Forbidden logs", text)
        self.assertIn("This ADR does not approve", text)
        self.assertIn("real personal memory storage", text)
        self.assertIn("Obsidian integration", text)
        self.assertIn("embeddings", text)
        self.assertIn("vector DB", text)
        self.assertIn("RAG", text)
        self.assertIn("AI durable writes", text)
        self.assertIn("API or Dashboard exposure", text)
        self.assertIn("Runtime execution", text)
        self.assertIn("Second Brain Phase 2 - SQLite Fixture Persistence", text)
        self.assertIn("Still prohibited", text)

    def test_wearable_boundary_adr_records_presence_signal_only(self):
        text = (
            REPO_ROOT / "docs" / "design" / "WEARABLE_BOUNDARY.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Status: Accepted / Design - Not Implemented", text)
        self.assertIn("Wearable Presence / Connection Context Source", text)
        self.assertIn("watch_connected", text)
        self.assertIn("Pixel Watch / Wear OS is the first implementation target", text)
        self.assertIn(
            "Closed-Device Research / Graceful Degradation Reference",
            text,
        )
        self.assertIn("blocked_by_platform", text)
        self.assertIn("requires_companion", text)
        self.assertIn("requires_permission", text)
        self.assertIn("separate from executable `DeviceCapability`", text)
        self.assertIn("A known wearable client/probe currently appears connected", text)
        self.assertIn("It does not mean user presence", text)
        self.assertIn("Wearable signal\n-> Runtime action", text)
        self.assertIn("`wearable_available`", text)
        self.assertIn("`user_authenticated`", text)
        self.assertIn("Wearable Phase 1 must not deliver notifications", text)
        self.assertIn("Connection status is personal context", text)
        self.assertIn("no provider or cloud exposure by default", text)
        self.assertIn("no `DeviceState` mutation", text)
        self.assertIn("no `Command` construction", text)
        self.assertIn("Sensitive Wearable Context ADR", text)
        self.assertIn("Adaptive Wake remains design-only", text)
        self.assertIn("no microphone or speaker assumption", text)
        self.assertIn("This ADR does not approve", text)
        self.assertIn("Wearable Phase 1 - Wear OS Presence / Connection Signal", text)

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

    def test_dashboard_hardware_validation_documents_manual_gate(self):
        guide = REPO_ROOT / "docs" / "dashboard" / "HARDWARE_VALIDATION.md"
        text = guide.read_text(encoding="utf-8")

        self.assertIn("python -m jarvis_core.dashboard", text)
        self.assertIn("profiles/http-lab.local.json", text)
        self.assertIn("device read lamp_1 status.read", text)
        self.assertIn("device apply lamp_1 power.switch state=true", text)
        self.assertIn("state/http-lab.state.json", text)
        self.assertIn("HARDWARE_DASHBOARD_VALIDATION_REQUIRED", text)
        self.assertIn("PHYSICAL_LED_ON_CONFIRMATION_PENDING", text)
        self.assertIn("No AI provider is required", text)

    def test_mqtt_driver_documentation_states_request_response_boundary(self):
        guide = REPO_ROOT / "docs" / "drivers" / "MQTT_DRIVER.md"
        text = guide.read_text(encoding="utf-8")

        self.assertIn("Experimental Request-Response Driver", text)
        self.assertIn("read(device, capability_name) -> DriverResult", text)
        self.assertIn("mqtt_bindings", text)
        self.assertIn("request_id", text)
        self.assertIn("No AI provider", text)
        self.assertIn("MQTT Local Broker Validation", text)
        self.assertIn("Phase 12.4 remains blocked", text)
        self.assertNotIn("Mosquitto setup", text.split("## Testing", 1)[0])

    def test_mqtt_validation_documentation_states_loopback_boundary(self):
        guide = REPO_ROOT / "docs" / "drivers" / "MQTT_VALIDATION.md"
        text = guide.read_text(encoding="utf-8")

        self.assertIn("tools/mosquitto-loopback.conf", text)
        self.assertIn("listener 1883 127.0.0.1", text)
        self.assertIn("python tools\\mqtt_simulated_lamp.py", text)
        self.assertIn("profiles\\mqtt-lab.example.json", text)
        self.assertIn("No AI provider", text)
        self.assertIn("Phase 12.4 remains blocked", text)
        self.assertNotIn("0.0.0.0", text.split("Do not use:", 1)[0])


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
