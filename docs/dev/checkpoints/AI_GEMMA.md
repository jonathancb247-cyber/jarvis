# AI Gemma Local Provider — Checkpoint

Branch: `feat/gemma-local-provider`

---

## Already Integrated

- AIProvider / AIActionPlan architecture
- Structured AI Bake-Off
- Ollama/Qwen baseline

---

## Uncommitted Gemma Files

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

- Gemma provider: 14 tests OK
- Android bridge: 13 tests OK
- Full suite: 794 tests OK
- `python -m jarvis_core`: safe exit

---

## Next Gate

Commit/review current Gemma provider + bridge work.
After merge, create separate workstream for Android LiteRT-LM companion.

---

## Context Policy

Future agents: read `AGENTS.md` + this checkpoint first. Avoid rediscovering closed decisions.
