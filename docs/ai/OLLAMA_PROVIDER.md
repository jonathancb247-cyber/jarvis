# Local Ollama Provider

Status: Experimental / Optional Local Provider

JarvisOS includes an optional Ollama provider boundary for local manual
validation of the AI Adapter. It is not wired into the default runtime, Runtime
API or Dashboard.

## Boundary

```text
Spanish user request
-> AISafeContext
-> OllamaAIProvider
-> localhost Ollama HTTP response
-> raw Structured Plan payload
-> existing AI Adapter normalization and validation
-> canonical command text
-> Planner
-> Runtime
```

The provider returns raw Structured Plan payloads. It does not create
`Command`, call Runtime, call drivers, mutate registries, write State Store, or
perform confirmation.

## Localhost Only

The provider accepts only a localhost Ollama base URL. The default is:

```text
http://127.0.0.1:11434
```

It rejects public hosts, LAN hosts, `0.0.0.0`, `.local` names, credentials,
queries, fragments, and arbitrary paths.

## Model Guidance

The first manual validation model for the current validated laptop is:

```text
qwen3:1.7b
```

`qwen3:4b` is conditional on a clean session with enough available RAM.
`qwen3:8b` is not recommended for the validated host.

The model is supplied explicitly. JarvisOS does not install Ollama, download
models, start Ollama, or pick a default provider.

## Request Strategy

The provider sends a bounded non-streaming JSON request to Ollama. It uses
Ollama JSON mode and sets `think` to `false` for short command-planning
requests.

A concrete JSON Schema was evaluated for the Ollama `format` field, but it is
not enabled in the initial local validation path because the validated CPU-first
host timed out under the 30 second policy during diagnostic testing. JarvisOS
therefore keeps schema enforcement in its own strict normalizer and validator.

The prompt contains:

- concise system instructions;
- the Spanish user request;
- serialized safe semantic context;
- AIActionPlan schema version 1;
- approved command grammar;
- bounded examples.

It excludes bindings, URLs, IP addresses, State Store paths, Runtime internals,
Driver results, secrets, diagnostics, and unrestricted history.

Canonical JarvisOS command text remains technical English, for example:

```text
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
device list
```

The model is instructed to return the `AIActionPlan` object directly at the JSON
root. A narrow compatibility path unwraps the real Qwen/Ollama shape
`{"actionPlan": {...}}` when `actionPlan` is the only top-level field. This does
not bypass the existing strict normalizer, Planner validation or policy checks.

## Limits

- one provider request at a time in the local validation path;
- non-streaming output;
- non-thinking request mode where supported by Ollama;
- 30 second default timeout;
- no automatic retries;
- bounded response size;
- strict JSON decoding;
- no prompt or provider response logging by default.

## Diagnostics

The AI-local entry point supports an explicit `--diagnostic` option for manual
validation. It may print only safe stage information, such as envelope keys,
response byte length, top-level JSON fields and validation stage. It does not
print raw prompts, raw provider responses, device bindings, stack traces or
secrets.

## Safe Errors

Provider failures are normalized to adapter-facing error codes such as:

- `ai_provider_unavailable`
- `ai_provider_timeout`
- `ai_model_not_found`
- `ai_model_unavailable`
- `ai_response_invalid`
- `ai_response_too_large`
- `ai_provider_protocol_error`

Raw provider payloads, endpoint details, stack traces, exception text and model
filesystem details are not exposed.

## Not Implemented

- OpenAI or any remote provider;
- provider registry;
- credentials or secrets store;
- streaming;
- retries;
- persistent AI memory;
- Dashboard AI chat;
- voice, vision or autonomous workflows.

See [Local AI Validation](LOCAL_AI_VALIDATION.md) for the manual gate.
