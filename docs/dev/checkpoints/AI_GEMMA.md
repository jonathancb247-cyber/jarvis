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

---

## Next Gate

Active workstream: **Android LiteRT-LM companion**.

Define and implement the minimal Android companion app that:
- satisfies `POST /generate`;
- runs Gemma local/offline;
- automatic tool execution disabled.

---

## Context Policy

Future agents: read `AGENTS.md` + this checkpoint first. Avoid rediscovering closed decisions.
