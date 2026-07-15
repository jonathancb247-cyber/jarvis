# Local AI Validation

Status: Manual Gate / Experimental

This guide validates the optional local Ollama provider after CI-safe tests pass.
CI must not require Ollama, a model, network access or credentials.

## Before Starting

Use a clean Windows session when possible.

Recommended preparation for the validated host:

1. Restart Windows, or close heavy applications.
2. Avoid Chrome-heavy sessions, multiple ChatGPT windows, IDEs, virtual
   machines and unnecessary utilities during the test.
3. Recheck available RAM.
4. Start with `qwen3:1.7b`.
5. Try `qwen3:4b` only if approximately 7.5-9 GB RAM remains available after
   cleanup.
6. Do not use `qwen3:8b` on the validated laptop.

## Install Ollama Manually

Install Ollama from the official Ollama source. JarvisOS does not install
Ollama and does not download models automatically.

Pull the initial validation model manually:

```bash
ollama pull qwen3:1.7b
```

## Start JarvisOS AI-local

Use a local profile that already works with JarvisOS:

```bash
python -m jarvis_core.ai_local --config profiles/http-lab.local.json --model qwen3:1.7b
```

For safe provider-stage diagnostics during manual validation, add:

```bash
--diagnostic
```

Diagnostic output reports stages and field names only. It does not print raw
prompts, raw provider responses, bindings, secrets or stack traces.

The AI-local path is explicit and isolated. It does not enable AI in:

- `python -m jarvis_core`
- `python -m jarvis_core.api`
- `python -m jarvis_core.dashboard`

## Manual Scenarios

Read-only request:

```text
Lee el estado de la lampara.
```

Expected behavior:

- canonical command text remains English;
- read-only classification is deterministic;
- execution can proceed without confirmation if validation passes.

Mutation request:

```text
Enciende la lampara.
```

Expected behavior:

- mutation requires confirmation;
- the exact generated plan is shown;
- execution happens only after `confirm <REAL_PLAN_ID>`.

Cancellation:

```text
cancel <plan_id>
```

Expected behavior:

- the plan is not executed;
- confirmation state remains ephemeral.

Clarification and refusal should return safe adapter messages without Runtime
execution.

## Optional ESP32 Validation

If the ESP32 profile is available, validate:

- turn LED on;
- read state;
- turn LED off;
- confirm no IP, URL, payload, stack trace or raw provider response appears in
  user-facing output.

## Evidence To Return

Record:

- available RAM before pulling/running the model;
- model name;
- startup command;
- read-only request result;
- mutation request result;
- confirmation result;
- clarification/refusal result;
- optional ESP32 LED evidence;
- approximate latency;
- observed memory impact;
- any safe error code.

Do not commit local profiles, real snapshots, IP addresses, SSIDs, passwords,
provider prompts or provider responses.
