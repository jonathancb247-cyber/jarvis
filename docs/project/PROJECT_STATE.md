# JarvisOS Project State

Status: Current / Project Snapshot

This document gives AI agents a compact project state snapshot. It points to the technical source documents instead of duplicating them.

For operational rules, read [../../AGENTS.md](../../AGENTS.md).

## Current Status

- Epics 1-9 are completed.
- Epic 10 is in progress.
- Phase 10.1 is completed as design: AI Adapter Boundary.
- Phase 10.2 is completed as design: Structured Plan and Safe Context Contracts.
- Phase 10.3 is completed: deterministic fake AI Adapter.
- Phase 10.4 is completed as design: First Optional Local AI Provider Boundary.
- Phase 10.5 is in progress / Draft: Ollama provider exists in PR #38, but no compatible local model has passed strict `AIActionPlan` validation.
- Phase 10.6 is completed as design: Optional Cloud AI Provider and Secret Injection Boundary.
- Phase 10.7 is in progress / Draft: Groq provider exists in PR #39, but real strict Structured Output validation is blocked by provider constrained generation.
- Phase 10.8 is completed as design: Gemini Structured Provider Boundary.
- Phase 10.9 is completed: Gemini Structured Provider Minimal Implementation merged in PR #41 and passed real provider validation.
- Phase 10.10 is blocked.
- Gemini is Current / Experimental: real provider validation passed with `gemini-3.6-flash`, full provider-neutral `AIActionPlan`, read, confirmed power on/off plans, ambiguity handling and destructive refusal.
- Ollama Local Provider Foundation is completed after PR #77 merge.
- Ollama Local Provider Foundation merge commit: `0a2d0b2d564d5d12ce4d01d41c0f828744030890`.
- Ollama Local Provider Foundation validation: fake-transport AI provider tests, explicit `ai_local` CLI tests, AI regression tests, 713-test full suite and default CLI smoke passed.
- Ollama Local Provider Foundation adds explicit `python -m jarvis_core.ai_local --provider ollama --model ...` usage with localhost-only `/api/chat`, `stream=false`, structured-output request shape, bounded transport and safe provider errors.
- PR #79 added explicit top-level `think:false` for Ollama structured-plan requests.
- PR #80 hardened the Ollama system instruction with mutually exclusive `AIActionPlan` prompt-shape guidance for execute, clarify and refuse plans.
- Ollama remains a Local Essential AI candidate through the explicit opt-in `ai_local` entry point. Real `qwen3:4b` structured planning has been validated for one bounded read case: the model produced `kind=execute`, canonical command `device read lamp_1 status.read`, `target_device_id=lamp_1`, `capability_name=status.read`, `action_kind=read`, no clarification/refusal and no confirmation requirement.
- The real `qwen3:4b` plan was accepted by the existing JarvisOS validation boundary and reached Runtime through the deterministic execution path; the physical HTTP device operation then failed with `device_timeout`, so physical device execution is not validated by this Ollama result.
- `qwen3:4b` is not declared generally reliable from this single validation case. Broader Real Ollama service/model validation is still pending, and broader local-model bakeoff remains future work.
- AI Router, provider registry, automatic provider fallback and automatic model switching remain unimplemented.
- No AI provider is default or production-ready.
- Epic 12 is in progress.
- Phase 12.1 is completed as design: MQTT Driver Boundary.
- Phase 12.2 is completed: MQTT Request/Response Driver Minimal Implementation merged in PR #43.
- MQTT Driver is Current / Experimental: synchronous request/response only with fake-client CI validation, per-device HTTP/MQTT composition, and Runtime shutdown ownership verified.
- Phase 12.3 is completed: Local Mosquitto Integration Validation merged in PR #45.
- Phase 12.4 is blocked until explicitly opened for ESP32 MQTT reference node work.
- Voice Phase 1 is completed: Voice Experience Benchmark Harness - Fake Providers Only merged in PR #49.
- Voice Phase 1 merge commit: `1b4c6f7821900a55681087ffe8c591fd92b3f6c3`.
- Voice Phase 1 validation: 560 tests passing and default CLI smoke passed.
- Voice Phase 1 is fake-only: deterministic benchmark scenarios, fake STT/TTS providers, simulated metrics, and no real microphone, speaker, provider, network, cloud, hardware, Runtime/Driver execution path, persistent Conversation Session, or Second Brain.
- Voice Phase 1 does not provide real voice capability, real latency measurements, or provider compatibility.
- Voice Phase 2A is completed: STT/TTS Provider Bake-Off Foundation merged in PR #51.
- Voice Phase 2A merge commit: `6bcde6bade0e596789e27e142b3f2f66edbed2c9`.
- Voice Phase 2A implementation commit: `1f41b75aa053f7242731a568e661d4411ffbbf1f`.
- Voice Phase 2A validation: 581 tests passing and default CLI smoke passed.
- Voice Phase 2A provides provider-neutral STT/TTS evaluation contracts, synthetic/text-only fixture taxonomy, mock provider paths, normalized failure categories, a bake-off report model and synthetic/test metrics only.
- Voice Phase 2A does not validate real STT compatibility, real TTS compatibility, real provider latency, naturalness, real prerecorded-audio STT, real file-output TTS, microphones, speakers, credentials, network, cloud, hardware or Runtime/API/Dashboard/Driver/AI behavior.
- Cognitive Phase 1 is completed: Deterministic Cognitive Vertical Slice merged in PR #58.
- Cognitive Phase 1 merge commit: `bc92c31992544f6d3824a7a1a39666b405977b23`.
- Cognitive Phase 1 validation: 609 tests passing and default CLI smoke passed.
- Cognitive Phase 1 implements a fake deterministic in-memory flow: scripted evidence -> Context -> Learning plus seeded read-only Memory -> Judgment -> Attention -> deterministic report.
- Cognitive Phase 1 validates Deep Focus, Night Mode Suggestion, Stale Device, Explicit User Correction, Private Notification and Habit Proposal scenarios.
- Cognitive Phase 1 is recommendation/report-only: Memory is seeded/read-only, Learning produces deterministic pattern evidence only, Context uses scripted explicit/inferred signals, Judgment recommends/defers/clarifies/abstains only and Attention selects fake defer/silence/surface outcomes only.
- Cognitive Phase 1 validates deterministic reports, safe explanations, explicit-over-inferred precedence, sensitive notification fake-surface privacy and that learned patterns do not automatically create Memory, Rules or Delegation.
- Cognitive Phase 1 does not implement real cognition quality, persistent Memory, persistent Learning, Context persistence, real sensors, phone/watch/vehicle input, AI-assisted cognition, fuzzy logic, notifications, real Attention surfaces, Voice integration, API/Dashboard exposure, Policy integration, Runtime integration, Planner integration, Driver execution, DeviceState mutation, delegated autonomy or multi-user cognition.
- Cognitive Phase 1 uses no persistence, network, providers, hardware, microphone/speaker, notification delivery or Runtime/Planner/Driver execution path.
- Cognitive Phase 2 is completed: Local Cognitive Report Surface merged in PR #60.
- Cognitive Phase 2 merge commit: `9f2da69e0c8b9130bde13757d82982f5f8a1d56c`.
- Cognitive Phase 2 validation: 617 tests passing, default CLI smoke passed, cognitive text smoke passed and cognitive JSON smoke passed.
- Cognitive Phase 2 reuses the Phase 1 deterministic cognitive benchmark unchanged and renders all six cognitive scenarios: Deep Focus, Night Mode Suggestion, Stale Device, Explicit User Correction, Private Notification and Habit Proposal.
- Cognitive Phase 2 provides local diagnostic text and canonical JSON report output through `python -m jarvis_core.cognitive` and `python -m jarvis_core.cognitive --format json`.
- Cognitive Phase 2 text and JSON output are deterministic and remain diagnostic/local only.
- Cognitive Phase 2 does not introduce execution authority, product-facing cognitive UI, Runtime integration, Runtime API cognitive endpoints, Dashboard cognitive panels, Voice integration, AI-assisted cognition, provider-backed cognition, persistence, network, hardware, real sensors, notification delivery, action buttons, policy integration, confirmation integration, delegated autonomy or real-world cognition quality validation.
- Cognitive Phase 2 has no Runtime/Planner/Driver path, DeviceState mutation, Command construction, API/Dashboard exposure, filesystem persistence by default, network/provider/hardware use or normal Jarvis CLI behavior change.
- Cognitive Phase 3 is completed: Read-Only DeviceState Cognitive Signal Mapping merged in PR #62.
- Cognitive Phase 3 merge commit: `be319286fa50fbc88df141995627d50d3b829ce3`.
- Cognitive Phase 3 validation: 629 tests passing, default CLI smoke passed, cognitive text smoke passed and cognitive JSON smoke passed.
- Cognitive Phase 3 is the first real JarvisOS semantic boundary entered cognition as evidence.
- Cognitive Phase 3 maps detached, read-only DeviceState semantic input into cognitive evidence; no live DeviceState object enters cognition.
- Cognitive Phase 3 mapping behavior: known/current -> fresh cognitive evidence; stale -> stale cognitive evidence; known/not-current -> conservatively stale; unknown -> insufficient low-confidence evidence with no fabricated properties.
- Cognitive Phase 3 keeps safe semantic properties bounded, immutable and filtered.
- Cognitive Phase 3 stale evidence produces read/clarify recommendation only and no explicit read occurs.
- Cognitive Phase 3 preserves Phase 1 and Phase 2 behavior unchanged, and existing diagnostic text/JSON reporting remains deterministic.
- Cognitive Phase 3 does not implement or validate Runtime integration, Runtime API cognition, Dashboard cognition, DeviceState mutation, device refresh, Driver execution, Planner execution, Command creation, hardware access, network access, persistence, AI/provider cognition, Voice integration, notification delivery, policy/confirmation integration, delegated autonomy, background polling, automatic scene activation, wearable integration or real-world cognitive accuracy.
- Cognitive Phase 3 has no Runtime/Planner/Driver/API/Dashboard/Voice/AI/State Store execution path, no persistence/network/hardware/provider use, and cognition treats DeviceState only as evidence.
- Wearable Phase 1 is completed: Wear OS Presence / Connection Signal merged in PR #66.
- Wearable Phase 1 merge commit: `9621d4197ed1cf2ca00d4be7bc791cfd6a19a9e3`.
- Wearable Phase 1 validation: 642 tests passing, default CLI smoke passed and existing six-scenario cognitive report smoke passed.
- Pixel Watch / Wear OS remains the first wearable implementation target, but Phase 1 is fake-first and deterministic only.
- Wearable Phase 1 implements exactly four fake wearable presence states: connected, disconnected, unknown and stale.
- Wearable Phase 1 uses a detached, frozen and read-only `WearablePresenceProjection`; fake fixtures map into cognitive evidence only.
- Wearable Phase 1 reuses existing Context, Judgment, Attention and local cognitive reporting. The existing six-scenario cognitive report remains unchanged.
- `watch_connected` means only that a known wearable probe appears connected. It does not imply user presence, watch wearing, awake state, user availability, identity/authentication, health or location.
- Degraded wearable states reduce wearable evidence only and do not create user absence, availability or identity inference.
- Wearable Phase 1 introduces no execution authority, Runtime action, Planner/Driver execution, DeviceState mutation, policy/confirmation integration, delegated autonomy, provider/cloud integration, persistence, network, hardware, Android/ADB integration, notifications, haptics, watch UI, microphone, speaker, Voice integration or real Wear OS probe.
- Wearable Phase 1 does not implement or validate real Pixel Watch connectivity, HR, HRV, sleep, activity/exercise, precise location, biometrics or wrist presence as identity.
- Sensitive Wearable Context remains blocked behind a future ADR/gate before health, sleep, activity, location or biometric signals enter cognition.
- Real Pixel Watch validation remains a separate future hardware gate; the future real Wear OS probe is expected to replace only the source side.
- Second Brain Phase 1 is completed: Deterministic In-Memory Knowledge Retrieval merged in PR #69.
- Second Brain Phase 1 merge commit: `fbb64eac19f8f880794322ac647ac8040ba069b2`.
- Second Brain Phase 1 validation: 656 tests passing, default CLI smoke passed, deterministic text diagnostic passed and deterministic JSON diagnostic passed.
- Second Brain Phase 1 is fake, deterministic and in-memory only, with seeded approved knowledge and deterministic retrieval through exact and normalized keyword-topic matching.
- Second Brain Phase 1 handles current, stale, historical, superseded and contradicted freshness; superseded evidence is retained but not treated as co-current.
- Second Brain Phase 1 applies deterministic source precedence: explicit correction outranks prior fact, equal-strength contradictions return contradicted rather than fabricated truth, and unknown queries return no fabricated answer.
- Second Brain Phase 1 provides deterministic text and JSON diagnostic output and no execution authority.
- Second Brain Phase 1 implementation snapshot: `jarvis_core/second_brain/__init__.py`, `jarvis_core/second_brain/__main__.py`, `jarvis_core/second_brain/models.py`, `jarvis_core/second_brain/fixtures.py`, `jarvis_core/second_brain/retrieval.py`, `jarvis_core/second_brain/reporting.py`, and `tests/test_second_brain_retrieval.py`.
- Second Brain Phase 1 example semantics remain conservative: the Pixel Watch fixture says fake/deterministic Wearable Phase 1 completed while real Pixel Watch hardware validation remains separate/pending, and the MQTT fixture represents local MQTT request/response validation without claiming physical ESP32 MQTT validation complete.
- Second Brain Phase 1 does not implement persistence, SQLite, JSON/file memory storage, durable memory, automatic memory extraction, automatic profiling, filesystem memory writes, network access, Notion/GitHub/Obsidian/Google Drive connectors, source indexing, embeddings, vector DB, semantic retrieval, RAG, AI/provider-backed retrieval, Runtime integration, Planner/Driver execution, DeviceState mutation, API/Dashboard integration, policy/confirmation changes or execution authority.
- Second Brain Phase 2 is completed: SQLite Fixture Persistence merged in PR #72.
- Second Brain Phase 2 merge commit: `f7c0f5e870c4c53886221264aa33bc2aee91c3df`.
- Second Brain Phase 2 validation: 675 tests passing, default CLI smoke passed, default deterministic in-memory Second Brain diagnostic passed and SQLite restart/correction/purge persistence proofs passed.
- Second Brain Phase 2 provides fixture-only SQLite persistence through Python stdlib `sqlite3`; SQLite is a storage adapter and not a core JarvisOS dependency.
- Second Brain remains in-memory by default. SQLite requires explicit diagnostic use with `--storage sqlite --db PATH`.
- Second Brain Phase 2 validates schema version 1, deterministic initialization/reload, duplicate ID rejection, explicit correction/supersession transactions, logical delete, hard purge, `user_scope` filtering/isolation, bounded `storage_corrupt` for malformed/incomplete schema, `schema_version_unsupported` for unsupported schema versions, no raw SQLite errors in reviewed public paths, and deterministic Phase 1 retrieval parity.
- Second Brain Phase 2 persistence proof: synthetic fixture data survives process restart, corrections survive restart with prior records retained as superseded, and hard-purged records remain absent after restart.
- Second Brain Phase 2 implementation snapshot: `jarvis_core/second_brain/repository.py`, `jarvis_core/second_brain/__init__.py`, `jarvis_core/second_brain/__main__.py`, `tests/test_second_brain_retrieval.py`, and `tests/test_second_brain_sqlite_repository.py`.
- Second Brain Phase 2 authorizes only synthetic ordinary/non-sensitive fixtures. PERSONAL, SENSITIVE and RESTRICTED durable data remain blocked, and fixture-only keyword guards are not a future real-memory safety model.
- Second Brain Phase 2 keeps State Store DeviceState-only; SQLite does not become Runtime, DeviceState or State Store persistence.
- Second Brain Phase 2 has no execution authority and does not implement real personal memory, sensitive memory, health memory, financial memory, relationship memory, private-message memory, precise-location memory, biometric memory, credentials/secrets, encryption, key management, backup/export, automatic memory extraction, automatic profiling, live source indexing, Notion/GitHub/Obsidian/Google Drive connectors, embeddings, vector DB, semantic retrieval, RAG, AI/provider-backed retrieval, AI durable writes, Runtime integration, Planner/Driver execution, DeviceState mutation, State Store reuse, API/Dashboard exposure, Voice memory integration, policy/confirmation changes or cloud/cross-device sync.
- Second Brain Phase 3/4 Foundation Slice is completed: Source Index and Hybrid Retrieval foundation merged in PR #74.
- Second Brain Phase 3/4 Foundation Slice merge commit: `ee7dc1cc918c2c14a50c9ce0c6bfa8e70ecc0c42`.
- Second Brain Phase 3/4 Foundation Slice validation: 694 tests passing, default CLI smoke passed, local Second Brain in-memory diagnostic passed, source-index diagnostic JSON smoke passed, source-index focused tests passed, Phase 1 retrieval regression passed and Phase 2 SQLite repository regression passed.
- Second Brain Phase 3/4 Foundation Slice implements local Markdown fixture source indexing only: `LocalMarkdownSourceAdapter` -> `SourceRecord` -> independent `SQLiteSourceIndex` -> `SourceHybridRetriever` -> `SourceRetrievalResult` -> local diagnostic.
- Second Brain Phase 3/4 Foundation Slice validates a nonrecursive bounded fixture source adapter, path and symlink escape protections, persistent local SQLite source index, deterministic source refresh, deterministic versioning and supersession, deleted-source reconciliation scoped by `source_scope`, deterministic lexical plus fake-semantic hybrid scoring, contradiction and authority handling, provenance-rich results and local CLI diagnostics.
- Second Brain Phase 3/4 Foundation Slice proof: source index persists and reopens with the same selected result; changed sources create a new current version and supersede the old version; deleted sources stop being current after refresh and reopen; equal-authority deliberate conflicts return contradicted; stronger authority conflicts select the stronger source while retaining weaker conflict evidence.
- Second Brain Phase 3 - Source Connectors / Indexing is FOUNDATION COMPLETE for local Markdown fixture indexing and bounded GitHub source adapter foundation only. Live GitHub validation and live Notion, Obsidian, Google Drive or other connectors remain future work.
- Second Brain Phase 4 - Semantic Retrieval / RAG is FOUNDATION COMPLETE for deterministic lexical plus fake-semantic scoring only. True semantic retrieval, embeddings, vector DB and RAG remain future work.
- Second Brain Phase 3/4 Foundation Slice has no execution authority and does not implement live source connectors, network source fetching, credentials/auth, real personal or sensitive memory, embeddings, vector DB, true semantic retrieval, RAG, AI/provider-backed retrieval, Runtime integration, Planner/Driver execution, DeviceState mutation, State Store reuse, API/Dashboard exposure, Cognition integration, policy/confirmation changes or cloud/cross-device sync.
- GitHub Source Adapter Foundation is completed after PR #76 merge.
- GitHub Source Adapter Foundation merge commit: `ec7b4dc2fc0e90ebbf641885306bed1689ff07a8`.
- GitHub Source Adapter Foundation validation: fake GitHub transport tests, source-index regression tests, 713-test full suite, default CLI smoke and local Second Brain diagnostic smoke passed.
- GitHub Source Adapter Foundation implements bounded GitHub source indexing through `GitHubSourceAdapter` -> `SourceRecord` -> `SQLiteSourceIndex` -> `SourceHybridRetriever` -> `SourceRetrievalResult` -> local diagnostic.
- GitHub Source Adapter Foundation keeps repository, ref and Markdown paths explicit and bounded; token input remains external only; tokens are not persisted, logged, copied into `SourceRecord` or forwarded to AI.
- GitHub Source Adapter Foundation preserves HTTPS/TLS verification, bounded timeouts and response sizes, safe connector error normalization, authority/provenance mapping and `source_scope` isolation.
- Live GitHub validation remains pending. This foundation does not implement Notion, Obsidian or Google Drive connectors and does not connect Second Brain to AI, RAG, Runtime, API, Dashboard or real personal/sensitive memory.
- Real personal memory still requires a separate Sensitive Memory / Retention / encryption gate; live source connectors, true semantic retrieval/RAG/embeddings, AI-backed memory writes and Obsidian integration remain future work behind separate explicit gates.
- Current snapshot commit: `6bcde6bade0e596789e27e142b3f2f66edbed2c9`.
- Phase 10.3 PR: #32 merged.
- Phase 10.3 implementation commit: `e374d30f2c28865c82fcb880f7079974ea1dfca4`.
- Full test suite after Phase 10.3: 444 tests passing.
- Epic 11 is in progress.
- Phase 11.1 is completed as design: Runtime API and Dashboard Adapter Boundary.
- Phase 11.2 is completed: Local Runtime API Minimal Implementation.
- Phase 11.2 PR: #34 merged.
- Phase 11.2 implementation commit: `04dcef842784ad333c6f83226d09fb1d04183b64`.
- Full test suite after Phase 11.2: 461 tests passing.
- Runtime API is Current / Experimental.
- Runtime API is localhost-only REST/JSON with synchronous Runtime interaction.
- Runtime API submits canonical command text through the Runtime-owned boundary and exposes safe detached projections.
- Phase 11.3 is completed: Minimal Local Dashboard.
- Phase 11.3 PR: #36 merged.
- Phase 11.3 implementation commit: `575387a028586a7d51d0d46727b4d792ec95464d`.
- Phase 11.3 visual refinement commit: `1136bc89cba39a7ee09f3cd9b9f7c2156d76f5d3`.
- Full test suite after Phase 11.3: 471 tests passing.
- Dashboard is Current / Experimental.
- Dashboard is localhost-only, API-backed, responsive, and built with vanilla HTML/CSS/JavaScript.
- Dashboard uses capability-driven controls from formal API capabilities.
- Dashboard has no external frontend dependencies, AI chat, auth, LAN access, WebSocket, SSE or async Runtime.
- Phase 11.4 - Profile-based Hardware Dashboard Validation is completed.
- Phase 11.4 final validation: ESP32 HTTP Dashboard path physically validated after PR #48 freshness fix merge; real read produced `known/current`, physical disconnect plus explicit read produced `stale/not current` with prior semantic properties preserved, and reconnect plus explicit read restored `known/current`.
- Phase 11.4 DeviceState freshness evidence: `power=false` was preserved during the failed disconnected read; no public transport URL, IP, socket, exception or driver details leaked into semantic properties or API/Dashboard responses.
- Phase 11.4 scope boundary: explicit `status.read` refreshes physical freshness in the current implementation. Dashboard auto-refresh refreshes projected Runtime API state only and does not imply hardware polling, heartbeat, automatic offline detection, MQTT availability monitoring or automatic discovery.
- Phase 11.4 validation notes: `stale` is not `unavailable`; `stale` means prior semantic state exists but is not confirmed current. The HTTP ESP32 path remains experimental and is not production-secure transport.
- Full test suite after PR #48 merge and Phase 11.4 closure: 595 tests passing.
- Phase 11.5 remains blocked.
- Current closing commit for Epic 9: `c3a6f78a72b9c08db550743cec6910934c44899d`.
- Full test suite at Epic 9 close: 420 tests passing.
- Default runtime remains empty, simulated, and offline-safe.

## Current Architecture

Runtime execution:

```text
CLI / Adapter
-> Planner
-> Runtime
-> Runtime Capability
-> DeviceCommandRouter
-> Driver
-> DriverResult
-> DeviceStateCoordinator
-> DeviceState
-> CapabilityResult
```

Configuration and persistence:

```text
JSON config
-> RuntimeConfigurationLoader
-> RuntimeProfile
-> bootstrap
-> DeviceRegistry
-> HttpDeviceBindingStore
-> optional JsonDeviceStateStore restore
-> Runtime
-> official DeviceState update
-> PersistingDeviceStateCoordinator
-> atomic snapshot
```

## Completed Epics

- Epics 1-2: runtime, adapter boundary, events, diagnostics, and CLI foundation.
- Epics 3-4: device domain, simulated driver boundary, routing, state coordination, and runtime bridge.
- Epics 5-6: device catalog and lifecycle.
- Epic 7: simulated discovery and onboarding.
- Epic 8: first experimental real driver through HTTP local, plus ESP32 hardware validation.
- Epic 9: JSON configuration, RuntimeProfile, DeviceState persistence, profile-based HTTP validation, and consolidation.

## Current Epic

Epic 10 — AI Adapter Boundary.

Current status:

- Phase 10.3 - Deterministic Fake AI Adapter Minimal Implementation is completed.
- Phase 10.5 - Local Ollama Provider Minimal Implementation remains in progress / Draft in PR #38.
- Phase 10.7 - Groq Strict Structured Provider Minimal Implementation remains in progress / Draft in PR #39.
- Phase 10.8 - Gemini Structured Provider Boundary is completed as architectural design.
- Phase 10.9 - Gemini Structured Provider Minimal Implementation is completed after PR #41 merge.
- Phase 10.10 - Real Provider Validation and Consolidation is blocked.
- Gemini provider work is Current / Experimental and real-provider validated with `gemini-3.6-flash`.
- Ollama Local Provider Foundation is completed after PR #77 merge as a fake-transport validated `ai_local` foundation. PR #79 added `think:false`, PR #80 hardened prompt-shape guidance, and one real `qwen3:4b` bounded read plan has passed existing `AIActionPlan` validation and reached Runtime; broader local-model bakeoff and physical device execution remain future work.
- Groq remains the voice/low-latency research lane and PR #39 remains Draft research, not a validated structured-planning provider.
- Epic 10 remains in progress: deterministic AI Adapter implemented; Gemini real provider validated; Ollama local foundation implemented with one bounded qwen3:4b real-model validation case; broader validation remains pending; Groq remains a research Draft path.

Independent product line:

- Epic 11 - Runtime API and Dashboard is in progress.
- Phase 11.2 - Local Runtime API is completed.
- Phase 11.3 - Minimal Local Dashboard is completed.
- Phase 11.4 - Profile-based Hardware Dashboard Validation is completed after physical ESP32 HTTP freshness validation.
- Phase 11.5 remains blocked.
- Epic 10 remains unchanged.
- Epic 11 status: In progress - Local Runtime API and Minimal Dashboard implemented; hardware Dashboard validation completed with physical ESP32 HTTP freshness evidence.

Independent transport line:

- Epic 12 - Driver and MQTT Expansion is in progress.
- Phase 12.1 - MQTT Driver Boundary is completed as architectural design.
- Phase 12.2 - MQTT Request/Response Driver Minimal Implementation is completed after PR #43 merge.
- Phase 12.2 merge commit: `80e83fc77534e96da74dc440942845f911ae47b4`.
- Phase 12.2 validation: 529 tests passing, default CLI, profile CLI, API-only and Dashboard regressions passed.
- MQTT remains Current / Experimental: synchronous request/response only; HTTP remains supported; real local loopback Mosquitto validation was completed in PR #45; ESP32 MQTT, LAN/public MQTT, subscriptions, retained state, retries, MQTT auth/TLS and broker credentials are not validated or implemented.
- Phase 12.3 - Local Mosquitto Integration Validation is completed after validating a real loopback Mosquitto broker, Paho MQTT client adapter, local simulated MQTT lamp, read/on/off, persistence/restart, correlation failures, simulator failure/recovery, API/Dashboard projection and HTTP regression.
- Phase 12.3 merge commit: `871f5f02cdac5f00741534d3f87e2a799d060417`.
- Phase 12.3 validation: 538 tests passing, default CLI, HTTP profile CLI, API-only and Dashboard regressions passed.
- Phase 12.3 validation remains local only: no ESP32 MQTT hardware, MQTT auth/TLS, retained state, subscriptions, retries, cloud broker or Dashboard MQTT UI.
- Phase 12.4 - ESP32 MQTT Reference Node is blocked until explicitly opened.

Independent voice line:

- Voice Phase 1 - Voice Experience Benchmark Harness: Fake Providers Only is completed after PR #49 merge.
- Voice Phase 1 merge commit: `1b4c6f7821900a55681087ffe8c591fd92b3f6c3`.
- Voice Phase 1 implementation commit: `44b63731bc7d05931c0d6f2c47d33a180b439262`.
- Voice Phase 1 validation: 560 tests passing and default CLI smoke passed.
- Voice Phase 1 provides deterministic fake/scripted STT and TTS providers, minimal Turn Manager and in-memory Conversation Session behavior, fake intent/confirmation outcomes, simulated metrics, compact reports and safety-invariant tests.
- Voice Phase 1 does not provide real voice capability, real audio I/O, real STT/TTS provider compatibility, real-world latency measurements, wake-word behavior, AEC, realtime voice, hardware validation, Runtime/Driver execution, persistent Conversation Session, Second Brain, network, cloud, credentials or provider calls.
- Voice Phase 2A - STT/TTS Provider Bake-Off Foundation is completed after PR #51 merge.
- Voice Phase 2A merge commit: `6bcde6bade0e596789e27e142b3f2f66edbed2c9`.
- Voice Phase 2A implementation commit: `1f41b75aa053f7242731a568e661d4411ffbbf1f`.
- Voice Phase 2A validation: 581 tests passing and default CLI smoke passed.
- Voice Phase 2A provides provider-neutral STT/TTS evaluation contracts, synthetic/text-only fixture taxonomy, mock/fake provider paths, normalized failure categories, a bake-off report model and synthetic/test metrics only.
- Voice Phase 2A does not provide or validate real STT compatibility, real TTS compatibility, real provider latency, naturalness, real prerecorded-audio STT, real file-output TTS, microphone access, speaker output, network, cloud, credentials, hardware or Runtime/API/Dashboard/Driver/AI behavior.

Independent cognitive line:

- Cognitive Phase 1 - Deterministic Cognitive Vertical Slice is completed after PR #58 merge.
- Cognitive Phase 1 merge commit: `bc92c31992544f6d3824a7a1a39666b405977b23`.
- Cognitive Phase 1 implementation commit: `4e50b9d9970f794c0b88a0a9a9a4b58212170b98`.
- Cognitive Phase 1 validation: 609 tests passing and default CLI smoke passed.
- Cognitive Phase 1 provides a fake deterministic in-memory recommendation/report slice that composes Context, Learning, seeded read-only Memory, Judgment and Attention without execution authority.
- Cognitive Phase 1 does not provide or validate persistent Memory, persistent Learning, Context persistence, real sensors, real notification delivery, real Attention surfaces, Voice integration, API/Dashboard exposure, AI-assisted cognition, fuzzy logic, policy integration, Runtime integration, Planner integration, Driver execution, DeviceState mutation, delegated autonomy or multi-user cognition.
- Cognitive Phase 2 - Local Cognitive Report Surface is completed after PR #60 merge.
- Cognitive Phase 2 merge commit: `9f2da69e0c8b9130bde13757d82982f5f8a1d56c`.
- Cognitive Phase 2 validation: 617 tests passing, default CLI smoke passed, local cognitive text report smoke passed and local cognitive JSON report smoke passed.
- Cognitive Phase 2 provides a local diagnostic report surface for the existing Phase 1 benchmark through `python -m jarvis_core.cognitive` and `python -m jarvis_core.cognitive --format json`.
- Cognitive Phase 2 remains non-executing and local-only: no Runtime, Planner, Driver, DeviceState, API, Dashboard, Voice, AI/provider, persistence, network, hardware, notification delivery, policy, confirmation or delegated autonomy path.
- Cognitive Phase 3 - Read-Only DeviceState Cognitive Signal Mapping is completed after PR #62 merge.
- Cognitive Phase 3 merge commit: `be319286fa50fbc88df141995627d50d3b829ce3`.
- Cognitive Phase 3 implementation commit: `d6695cd226718d8880ae9d4e88b16b6656f146b5`.
- Cognitive Phase 3 validation: 629 tests passing, default CLI smoke passed, local cognitive text report smoke passed and local cognitive JSON report smoke passed.
- Cognitive Phase 3 is the first real JarvisOS semantic boundary to enter cognition as detached read-only evidence: no live DeviceState object enters cognition, safe semantic properties are bounded, immutable and filtered, and cognition treats DeviceState only as evidence.
- Cognitive Phase 3 mapping behavior is explicit: known/current -> fresh cognitive evidence; stale -> stale cognitive evidence; known/not-current -> conservatively stale; unknown -> insufficient low-confidence evidence with no fabricated properties.
- Cognitive Phase 3 remains recommendation/report-only: stale evidence can produce read/clarify recommendations, but no explicit read occurs and no Runtime/Planner/Driver/API/Dashboard/Voice/AI/State Store execution path is introduced.
- Cognitive Phase 3 does not provide or validate Runtime integration, Runtime API cognition, Dashboard cognition, DeviceState mutation, device refresh, Driver execution, Planner execution, Command creation, hardware access, network access, persistence, AI/provider cognition, Voice integration, notification delivery, policy/confirmation integration, delegated autonomy, background polling, automatic scene activation, wearable integration or real-world cognitive accuracy.

Independent wearable line:

- Wearable Boundary ADR is accepted for Wear OS Presence / Connection Signal.
- Wearable Phase 1 - Wear OS Presence / Connection Signal is completed after PR #66 merge.
- Wearable Phase 1 merge commit: `9621d4197ed1cf2ca00d4be7bc791cfd6a19a9e3`.
- Wearable Phase 1 validation: 642 tests passing, default CLI smoke passed and existing six-scenario cognitive report smoke passed.
- Wearable Phase 1 provides a fake deterministic local slice for `watch_connected` using detached read-only wearable projections and cognitive evidence mapping only.
- Wearable Phase 1 remains non-executing and fake-only: no real Pixel Watch connectivity, Wear OS app/probe, Android/ADB integration, hardware access, network transport, notifications, haptics, watch UI, microphone, speaker, Voice, health signals, location, biometrics, persistence, provider/cloud integration, Runtime/Planner/Driver execution, DeviceState mutation, policy/confirmation integration or delegated autonomy.
- Sensitive Wearable Context remains blocked behind a future ADR/gate before HR, HRV, sleep, activity, precise location, biometrics or wrist-presence identity evidence enters cognition.
- Real Pixel Watch validation remains a separate future hardware gate.

Independent Second Brain line:

- Second Brain Phase 1 - Deterministic In-Memory Knowledge Retrieval is completed after PR #69 merge.
- Second Brain Phase 1 merge commit: `fbb64eac19f8f880794322ac647ac8040ba069b2`.
- Second Brain Phase 1 validation: 656 tests passing, default CLI smoke passed, local Second Brain text diagnostic passed and local Second Brain JSON diagnostic passed.
- Second Brain Phase 1 provides fake/deterministic/in-memory retrieval over seeded approved knowledge only, using exact and normalized keyword-topic matching.
- Second Brain Phase 1 handles freshness, supersession, contradiction and source precedence deterministically: explicit correction outranks prior fact, equal-strength contradictions return contradicted, and unknown queries return no fabricated answer.
- Second Brain Phase 1 remains diagnostic/retrieval-only and has no execution authority.
- Second Brain Phase 1 does not provide or validate persistence, SQLite, file-backed memory, durable memory, automatic memory extraction, automatic profiling, filesystem memory writes, source indexing, connectors, embeddings, vector DB, semantic retrieval, RAG, AI/provider-backed retrieval, Runtime integration, Planner/Driver execution, DeviceState mutation, API/Dashboard integration, policy/confirmation changes or execution authority.
- Second Brain Phase 2 - SQLite Fixture Persistence is completed after PR #72 merge.
- Second Brain Phase 2 merge commit: `f7c0f5e870c4c53886221264aa33bc2aee91c3df`.
- Second Brain Phase 2 validation: 675 tests passing, default CLI smoke passed, local Second Brain in-memory diagnostic passed and SQLite restart/correction/purge persistence proofs passed.
- Second Brain Phase 2 provides explicit fixture-only SQLite persistence through Python stdlib `sqlite3`; SQLite remains a storage adapter, not a core JarvisOS dependency, and in-memory remains the default Second Brain mode.
- SQLite mode is explicit through `--storage sqlite --db PATH`; no hidden automatic seeding is performed.
- Second Brain Phase 2 validates schema version 1, deterministic initialization/reload, duplicate ID rejection, explicit correction/supersession transactions, logical delete, hard purge, `user_scope` filtering/isolation, malformed/incomplete schema -> bounded `storage_corrupt`, unsupported schema version -> `schema_version_unsupported`, no raw SQLite errors in reviewed public paths, and deterministic Phase 1 retrieval parity.
- Second Brain Phase 2 persistence proof: synthetic fixtures survive process restart, corrections survive restart, prior records remain superseded, and hard-purged records remain absent after restart.
- Second Brain Phase 2 implementation snapshot: `jarvis_core/second_brain/repository.py`, `jarvis_core/second_brain/__init__.py`, `jarvis_core/second_brain/__main__.py`, `tests/test_second_brain_retrieval.py`, and `tests/test_second_brain_sqlite_repository.py`.
- Second Brain Phase 2 keeps boundaries explicit: only synthetic ordinary/non-sensitive fixtures are authorized; PERSONAL, SENSITIVE and RESTRICTED durable data remain blocked; fixture-only keyword guards are not a future real-memory safety model; State Store remains DeviceState-only; SQLite does not become Runtime/DeviceState persistence.
- Second Brain Phase 2 does not implement or validate real personal memory, sensitive memory, health memory, financial memory, relationship memory, private-message memory, precise-location memory, biometric memory, credentials/secrets, encryption, key management, backup/export, automatic memory extraction, automatic profiling, live source indexing, Notion/GitHub/Obsidian/Google Drive connectors, embeddings, vector DB, semantic retrieval, RAG, AI/provider-backed retrieval, AI durable writes, Runtime integration, Planner/Driver execution, DeviceState mutation, State Store reuse, API/Dashboard exposure, Voice memory integration, policy/confirmation changes, cloud/cross-device sync or execution authority.
- Second Brain Phase 3/4 Foundation Slice - Source Index and Hybrid Retrieval foundation is completed after PR #74 merge.
- Second Brain Phase 3/4 Foundation Slice merge commit: `ee7dc1cc918c2c14a50c9ce0c6bfa8e70ecc0c42`.
- Second Brain Phase 3/4 Foundation Slice validation: 694 tests passing, default CLI smoke passed, local Second Brain in-memory diagnostic passed, source-index diagnostic JSON smoke passed, source-index focused tests passed, Phase 1 retrieval regression passed and Phase 2 SQLite repository regression passed.
- Second Brain Phase 3/4 Foundation Slice provides local Markdown fixture source indexing only through `LocalMarkdownSourceAdapter`, `SourceRecord`, independent `SQLiteSourceIndex`, `SourceHybridRetriever`, `SourceRetrievalResult` and local diagnostic output.
- Second Brain Phase 3/4 Foundation Slice validates nonrecursive bounded local source indexing, path and symlink escape protections, deterministic source refresh, deterministic source versioning and supersession, source deletion reconciliation scoped by `source_scope`, provenance-rich results, deterministic lexical plus fake-semantic hybrid scoring, contradiction handling and authority precedence.
- Second Brain Phase 3/4 Foundation Slice proof: source index persists and reopens with the same selected result; changed sources create a new current version and supersede the old version; deleted sources stop being current after refresh and reopen; equal-authority deliberate conflicts return contradicted; stronger authority conflicts select the stronger source while retaining weaker conflict evidence.
- Second Brain Phase 3 - Source Connectors / Indexing is FOUNDATION COMPLETE for local Markdown fixture indexing and bounded GitHub source adapter foundation only; live GitHub validation and live Notion, Obsidian, Google Drive or other connectors remain future work.
- Second Brain Phase 4 - Semantic Retrieval / RAG is FOUNDATION COMPLETE for deterministic lexical plus fake-semantic scoring only; true semantic retrieval, embeddings, vector DB and RAG remain future work.
- Second Brain Phase 3/4 Foundation Slice remains diagnostic/retrieval-only and has no execution authority.
- Second Brain Phase 3/4 Foundation Slice does not implement or validate live GitHub source access, live Notion connectors, Obsidian integration, Google Drive connectors, credentials/auth, real personal memory, sensitive memory, embeddings, vector DB, true semantic retrieval, RAG, AI/provider-backed retrieval, AI durable writes, Runtime integration, Planner/Driver execution, DeviceState mutation, State Store reuse, API/Dashboard exposure, Cognition integration, policy/confirmation changes, cloud/cross-device sync or execution authority.
- GitHub Source Adapter Foundation is completed after PR #76 merge commit `ec7b4dc2fc0e90ebbf641885306bed1689ff07a8`.
- GitHub Source Adapter Foundation is fake-transport validated and adds bounded GitHub source indexing only; live GitHub validation remains pending.
- GitHub Source Adapter Foundation preserves explicit repo/ref/path scope, external-only token input, no token persistence/logging, HTTPS/TLS, bounded transport errors, authority/provenance mapping and `source_scope` isolation.
- Live Notion, Obsidian and Google Drive connectors remain future work. Second Brain -> AI integration, RAG, embeddings, vector DB and real personal/sensitive memory remain unimplemented.
- Real personal/sensitive memory, live connectors, true semantic retrieval/RAG/embeddings/AI, AI-backed memory writes and Obsidian integration remain future work behind separate explicit gates.

## Stable Boundaries

Stable project rules:

- Configuration is not State.
- State is not Secrets.
- RuntimeProfile is declarative.
- Runtime does not read files directly.
- DeviceRegistry does not read or write files.
- Drivers do not receive `Command`.
- Drivers do not return `CapabilityResult`.
- Drivers do not persist.
- Restored state becomes `stale`.
- `stale` does not imply current availability.

## Experimental Boundaries

Current experimental areas:

- HTTP local transport.
- `HttpDeviceDriver`.
- `HttpDeviceBindingStore`.
- JSON configuration schema v1.
- `JsonDeviceStateStore`.
- State snapshot schema v1.
- ESP32 HTTP LED validation workflow.
- Deterministic Fake AI Adapter.
- Optional Gemini Provider.
- Gemini AI-cloud entry point.
- Structured Plan models.
- Safe Context Builder.
- Plan Validator.
- Confirmation Gate.
- Sequential AI Plan Executor.
- Runtime API Adapter.
- Localhost REST/JSON Runtime API.
- Safe Runtime API projections.
- Minimal Local Dashboard.
- Vanilla Dashboard static assets.
- Profile-based Hardware Dashboard validation workflow.
- MQTT request/response driver boundary.
- MQTT profile binding model.
- MQTT fake-client validation workflow.
- Voice Experience Benchmark Harness.
- Fake STT/TTS providers.
- Minimal fake Turn Manager.
- In-memory fake Conversation Session.
- Simulated voice benchmark metrics.
- Deterministic Cognitive Vertical Slice.
- In-memory fake cognitive scenario runner.
- Seeded read-only cognitive Memory.
- Deterministic cognitive Learning, Context, Judgment and Attention components.
- Cognitive benchmark report metrics and safety invariant checks.
- Local Cognitive Report Surface.
- Deterministic cognitive text and JSON diagnostic report rendering.
- Read-only DeviceState cognitive signal mapping.
- Detached DeviceState semantic projections as cognitive evidence.
- Fake deterministic wearable presence signal mapping.
- Detached wearable semantic projections as cognitive evidence.
- Deterministic in-memory Second Brain retrieval.
- Seeded approved Second Brain knowledge fixtures.
- Local Second Brain text and JSON diagnostic report rendering.
- Fixture-only SQLite Second Brain persistence adapter.
- Local SQLite Second Brain diagnostic mode.
- Local Markdown Second Brain source indexing.
- Persistent SQLite Second Brain source index.
- Deterministic Second Brain hybrid retrieval with fake semantic scoring.

## Current Transports

- Current / Experimental: HTTP local.
- Current / Experimental: MQTT request/response with injected client.
- Current / Simulated: in-memory simulated driver.
- Future / Not Implemented: Serial/USB, GPIO, BLE, Zigbee, Tuya.

## Supported Platforms

See [platform guides](../platforms/README.md).

Current validated platform:

- ESP32 + ESP-IDF with HTTP local LED example.

Current host support:

- Linux PC.
- Windows PC.

Future/reference only:

- ESP32 Arduino.
- ESP8266.
- Arduino Uno.
- STM32.
- Raspberry Pi GPIO.
- Android bridge/node.

## Validation Status

- CI uses fake transports and must not require hardware.
- ESP32 validation is manual.
- Profile-based hardware validation uses `python -m jarvis_core --config profiles/http-lab.local.json`.
- Runtime API validation uses `python -m jarvis_core.api --config profiles/http-lab.local.json`.
- The older `tools/run_http_led_validation.py` script remains a direct helper, not the primary profile-based validation path.

## Testing Status

Standard tests:

```bash
python -m unittest
```

Default smoke:

```bash
python -m jarvis_core
```

Configuration smoke:

```bash
python -m jarvis_core --config profiles/http-lab.example.json
```

Runtime API smoke:

```bash
python -m jarvis_core.api --config profiles/http-lab.example.json
```

Dashboard smoke:

```bash
python -m jarvis_core.dashboard --config profiles/http-lab.example.json
```

## Important Decisions

- GitHub is the source of truth for implementation, protocols, examples, exact commands, and platform integration guides.
- Notion is the source of truth for ADRs, architecture status, roadmap, development journal, and releases.
- Default runtime stays offline-safe and does not load devices, bindings, network, or State Store.
- Profiles are declarative data, not live objects or plugin systems.
- State Store persists only semantic `DeviceState`; it does not persist config, bindings, trust, candidates, diagnostics, raw payloads, or secrets.
- Hardware availability is never inferred from restored state.
- AI providers do not produce executable `Command` objects.
- AI Structured Plans are normalized and validated before canonical command text reaches the Runtime-owned adapter boundary.
- The deterministic fake AI Adapter uses no network, credentials, provider SDK, or real model.
- The default runtime remains AI-free.
- No provider registry exists.
- No persistent AI memory exists.
- Phase 10.3 did not change Runtime, Driver, Registry, Configuration, or State Store boundaries.
- Phase 10.9 does not wire Gemini into the default Runtime, Runtime API, or Dashboard.
- Gemini requires explicit `python -m jarvis_core.ai_cloud --provider gemini` usage and `GEMINI_API_KEY` in the active environment.
- Gemini real-provider validation passed in Phase 10.9 using `gemini-3.6-flash`, the full provider-neutral `AIActionPlan`, strict JarvisOS validation, confirmation flow and destructive refusal.
- Gemini TLS and hostname verification remain enabled through the reviewed provider transport.
- MQTT request/response support is experimental and validated with fake clients plus local loopback Mosquitto in PR #45.
- MQTT local broker validation uses loopback Mosquitto with a validation-only simulated lamp; it is not production MQTT or ESP32 MQTT validation.
- MQTT topics are binding/config data and must not appear in DeviceCapability, Runtime API, Dashboard or AI context.
- MQTT does not implement subscriptions, retained state, LWT, availability topics, credentials, retries or background state updates.
- The Runtime API is optional, localhost-only, and submits canonical command text through the existing Runtime-owned adapter boundary.
- The Runtime API exposes detached semantic projections only.
- The Runtime API remains the boundary consumed by the Dashboard and still does not implement LAN access, authentication, WebSocket, SSE, async Runtime, or direct internal access.
- The Dashboard is optional, local-only, API-backed, and does not import Runtime internals.
- Cognitive Phase 1 is fake, deterministic, in-memory and recommendation/report-only.
- Cognitive Phase 1 has no execution authority and no Runtime, Planner, Driver, DeviceState, API, Dashboard, AI, Voice, persistence, network, provider, hardware, microphone/speaker or notification-delivery path.
- Cognitive Phase 1 learned patterns do not automatically create Memory, Rules or Delegation.
- Cognitive Phase 2 is diagnostic/local only and has no execution authority.
- Cognitive Phase 2 does not change the normal Jarvis CLI and does not expose cognition through Runtime API or Dashboard.
- Cognitive Phase 3 lets cognition consume detached DeviceState semantic projections as evidence only.
- Cognitive Phase 3 does not perform device refreshes, explicit reads, Runtime actions, Planner actions, Driver calls or DeviceState mutation.
- Cognitive Phase 3 preserves deterministic local cognitive reporting and introduces no API, Dashboard, Voice, AI/provider, persistence, network, hardware, notification-delivery or State Store path.
- Wearable Phase 1 lets cognition consume fake detached wearable presence projections as evidence only.
- `watch_connected` does not imply presence, watch wearing, wakefulness, availability, identity, health or location.
- Real Pixel Watch validation and Sensitive Wearable Context remain separate future gates.

## Out Of Scope

Not currently implemented:

- production AI providers;
- automatic provider fallback;
- `--profile`;
- DriverRegistry;
- retries/backoff;
- async/background I/O;
- secrets store;
- production authentication or authorization;
- migrations;
- Dashboard validation beyond the Phase 11.4 profile-based hardware Dashboard validation;
- MQTT over LAN, public MQTT, cloud MQTT, production broker deployment or broker UI;
- ESP32 MQTT node validation;
- MQTT subscriptions, retained messages, availability topics, TLS/authentication or credentials;
- hardware discovery;
- persistent trust;
- persistent AI memory;
- AI/LLM scenario engine behavior;
- persistent cognitive Memory or Learning;
- Context persistence;
- real cognitive sensors;
- real Attention notification delivery;
- cognitive Runtime/Planner/Driver execution authority;
- cognitive DeviceState mutation or device refresh;
- product-facing cognitive UI;
- Runtime API cognitive endpoints;
- Dashboard cognitive panels;
- Voice-connected cognition;
- AI-assisted cognitive recommendations;
- provider-backed cognition;
- real personal or sensitive Second Brain memory;
- encrypted Second Brain storage or key management;
- Second Brain backup/export;
- JSON/file-backed memory;
- automatic memory extraction;
- automatic profiling;
- Second Brain filesystem memory writes;
- live Notion, Obsidian or Google Drive Second Brain connectors;
- live GitHub source validation;
- embeddings, vector DB, semantic retrieval or RAG;
- AI/provider-backed Second Brain retrieval;
- real wearable integration beyond fake deterministic presence evidence;
- real Pixel Watch connectivity or Wear OS app/probe;
- Android/ADB wearable integration;
- wearable notifications, haptics, watch UI, microphone, speaker or Voice integration;
- HR, HRV, sleep, activity/exercise, precise location, biometrics or wrist presence as identity;
- cognitive background polling or automatic scene activation;
- real-world cognition quality validation;
- delegated cognitive autonomy;
- multi-user cognition.

## Key Technical Documents

- [Runtime Configuration](../getting-started/CONFIGURATION.md)
- [Device State Persistence](../getting-started/STATE_PERSISTENCE.md)
- [HTTP Profile Validation](../getting-started/HTTP_PROFILE_VALIDATION.md)
- [Runtime API](../api/README.md)
- [Dashboard](../dashboard/README.md)
- [Device Integration Guide](../device-integration/README.md)
- [Driver Development](../device-integration/DRIVER_DEVELOPMENT.md)
- [Security Guidelines](../device-integration/SECURITY_GUIDELINES.md)
- [ESP32 + ESP-IDF Guide](../platforms/ESP32_ESP_IDF.md)
- [HTTP LED Example](../../examples/http-led/README.md)
- [MQTT Driver](../drivers/MQTT_DRIVER.md)
- [AI Adapter](../ai/README.md)

## Glossary

- Runtime Capability: executable capability registered in `CapabilityRegistry`.
- DeviceCapability: semantic descriptor of what a device supports.
- DriverResult: internal technical result from a driver.
- DeviceState: official semantic state known by JarvisOS.
- RuntimeProfile: validated declarative configuration data.
- State Store: persistence boundary for semantic `DeviceState`.
- Binding: non-sensitive infrastructure configuration for reaching a device.
- Stale: restored last-known state that is not proof of current availability.
- AIActionPlan: provider-neutral structured plan normalized by the AI Adapter.
- AISafeContext: detached semantic context snapshot for AI planning.
- Runtime API: optional localhost adapter exposing safe REST/JSON projections and command submission.
- Dashboard: optional browser UI consuming the localhost Runtime API.

## Quick Onboarding For AI Agents

1. Read [../../AGENTS.md](../../AGENTS.md).
2. Read this file.
3. Inspect `git status -sb`.
4. Identify the requested phase and scope.
5. Read the referenced technical guide for the area being changed.
6. Do only the requested work.
7. Run `python -m unittest`.
8. Run relevant smoke tests.
9. Report scope confirmations explicitly.

