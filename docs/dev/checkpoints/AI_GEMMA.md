# AI Gemma Local Provider — Checkpoint

Branch: `feat/android-gemma-companion`

---

## Already Integrated

- AIProvider / AIActionPlan architecture
- Structured AI Bake-Off
- Ollama/Qwen baseline
- Local Gemma provider + Android bridge (merged into main via PR #88)

---

## Gemma Files (merged into main)

PR #88: merged

- `jarvis_core/ai/gemma_local.py`
- `jarvis_core/ai/gemma_android_bridge.py`
- `tests/test_gemma_local_provider.py`
- `tests/test_gemma_android_bridge.py`

---

## Architecture

```
JarvisOS
  -> GemmaLocalAIProvider
      -> GemmaLocalTransport
      -> GemmaAndroidBridgeTransport
          -> future Android companion
              -> LiteRT-LM
              -> Gemma local
```

Return path: Gemma output -> raw AIActionPlan-compatible payload -> existing normalize/validate/safety boundaries.

---

## Out of Scope

- Direct Android action execution
- Runtime/Drivers inside providers
- STT
- Cloud fallback
- AI selector
- Edge Gallery as production backend

---

## Decisions (closed)

- Edge Gallery is evaluation/reference only.
- Future Android execution: own companion app using LiteRT-LM.
- HTTP POST `/generate` is the current lab bridge contract.
- Automatic tool execution remains disabled.
- Tool calls may only translate to raw plan-compatible data.

---

## Verification

- Gemma provider: 15 tests OK
- Android bridge: 17 tests OK
- Full suite: 799 OK
- `python -m jarvis_core`: safe exit

### Gate 1 Android companion — physical bridge validation (passed)

The first real Android companion implementation at `companion/android/` (Gate 1,
fake-first) was built and physically validated on a POCO F5:

- Companion app runs on device `127.0.0.1:8767`; NanoHTTPD bound to loopback only.
- `adb forward tcp:8767 tcp:8767` active.
- Real `curl POST /generate -> HTTP 200` returning the fixed schema-valid
  `clarify` AIActionPlan.
- Python end-to-end smoke:
  `GemmaLocalAIProvider -> GemmaAndroidBridgeTransport(127.0.0.1:8767)
  -> adb forward -> companion -> fixed clarify plan -> existing JarvisOS
  normalization/validation` accepted the plan (`normalize_plan` + `validate_plan_shape`),
  latency ~26 ms.
- Request-body bug fixed: server now reads exactly `Content-Length` bytes via
  NanoHTTPD `session.parseBody` (not until EOF); regression test
  `postBodyWithContentLengthIsConsumedWithoutEofWait` added.
- Android unit tests: 14 OK.

Decisions recorded for Gate 1: loopback-only binding; NanoHTTPD embedded server;
minimal visible Activity (no foreground Service); no LiteRT-LM/model in Gate 1;
request limit 24 KiB. Gradle wrapper committed; `local.properties` ignored.

### Gate 2A Android LiteRT-LM inference probe (passed)

The isolated real Gemma inference probe was built and physically validated on a POCO F5.

**Stack:**
- LiteRT-LM `0.16.1` (Google Maven, pinned; not `latest.release`)
- Kotlin `2.3.21` (required for litertlm-android 0.16.1 metadata compatibility; AGP 8.7.3 / Gradle 8.9 unchanged)
- CPU backend only (`Backend.CPU()`)
- Model: Gemma 3 1B int4 (`.litertlm` format, 584417280 bytes, lives in app-private storage, not committed)

**Files (Gate 2A only):**
- `companion/android/build.gradle.kts` — Kotlin 2.3.21
- `companion/android/app/build.gradle.kts` — `litertlm-android:0.16.1` pin; compilerOptions DSL
- `companion/android/app/src/main/java/com/jarvisos/companion/GemmaEngine.kt` — wrapper + `LiteRtRuntime` (Session-based `generateContent`)
- `companion/android/app/src/main/java/com/jarvisos/companion/MainActivity.kt` — debug probe UI + busy state fix
- `companion/android/app/src/main/res/layout/activity_main.xml` — probe layout
- `companion/android/app/src/main/res/values/strings.xml` — probe strings
- `companion/android/app/src/test/java/com/jarvisos/companion/GemmaEngineTest.kt` — wrapper state/error tests

**Untouched by Gate 2A:**
- `GenerateServer.kt` — fake `POST /generate` remains unchanged
- `AndroidManifest.xml` — no GPU/NPU permissions
- Python code / Runtime / Drivers — untouched
- `examples/` — untouched

**Physical validation (POCO F5):**
- Model loaded from `/data/data/com.jarvisos.companion/files/gemma3-1b-it-int4.litertlm`
- Prompt: `"Reply exactly with: OK"`
- Real on-device inference output: `"OK"`

**Android build:** `:app:assembleDebug :app:testDebugUnitTest` — BUILD SUCCESSFUL, 34/34 tests OK
**Python:** 799 OK; `python -m jarvis_core`: safe exit

**Android unit tests:**
- 11 `GemmaEngineTest` (wrapper state/error behavior, no real model)
- 23 existing Android tests

Decisions recorded for Gate 2A: CPU-only for inference probe; LiteRT-LM `Session` API (`generateContent` returning plain `String`); wrapper seam for host unit testing; no connection to `GenerateServer` / fake `/generate`; model binary external / not committed.

---

### Gate 2B Android `/generate` real inference bridge (passed)

The companion `POST /generate` path was wired to the process-owned
`GemmaModelController` and physically validated on the POCO F5.

Validated infrastructure:
- real Android `/generate` bridge works through `adb forward tcp:8767 tcp:8767`;
- `GemmaModelController` owns the process-wide model/Engine;
- `GemmaJsonExtractor` conservatively accepts exactly one JSON object and rejects
  malformed, empty, multi-object or ambiguous model output;
- the LiteRT-LM Engine remains loaded process-wide;
- a fresh LiteRT-LM `Session` is created and closed for every `generate()`;
- inference access is serialized;
- safe HTTP errors are returned for missing model, bad request, invalid
  generation, oversized output and inference failure;
- loopback-only NanoHTTPD behavior remains unchanged;
- Android never executes tools, Runtime, Drivers or Android actions.

Physical result:
- fresh per-request sessions eliminated the previous warm-session
  `FAILED_PRECONDITION` / KV accumulation failure;
- warm physical latency was roughly 7-15 seconds for one inference after the
  Engine was loaded;
- Python `normalize_plan` / `validate_plan_shape` remains the final authority
  for AIActionPlan acceptance.

### Gate 2C Gemma 3 1B structured planning (failed / rejected)

Gemma 3 1B int4 was evaluated as the first local structured planner through the
validated Android bridge. It is not accepted as a JarvisOS structured planner.

Observed failure modes:
- one-shot prompt with a concrete clarify-only example anchored all responses to
  `clarify`;
- one-shot prompt with execute-first examples anchored responses to `execute`;
- one-shot prompt without examples lost the AIActionPlan structure and emitted
  irrelevant or context-derived JSON structures;
- a minimal two-stage experiment was tried and rejected:
  - `spanish_simple_read` classified as `refuse` instead of `execute`;
  - `ambiguous_device_clarify` classified as `execute` instead of `clarify`;
  - two-stage total latency was roughly 40 seconds for the first fixture.

Conclusion:
- Gate 2B infrastructure is successful and should be retained.
- Gate 2C structured planning with Gemma 3 1B failed semantically.
- Do not continue one-shot or two-stage prompt tuning for this model as a
  JarvisOS planner.
- Next recommendation: evaluate a different local planner model while reusing
  the validated Android bridge, process-owned Engine, fresh-session lifecycle,
  serialized access, conservative JSON extraction and Python validation
  authority.

## Next Gate

Gate 2B is closed as infrastructure. The next local-AI planner gate should be a
different model evaluation, not more prompt tuning of Gemma 3 1B.

---

## Context Policy

Future agents: read `AGENTS.md` + this checkpoint first. Avoid rediscovering closed decisions.
