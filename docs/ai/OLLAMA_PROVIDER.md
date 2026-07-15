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

The provider sends a bounded non-streaming JSON request to Ollama. The prompt
contains:

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

## Limits

- one provider request at a time in the local validation path;
- non-streaming output;
- 30 second default timeout;
- no automatic retries;
- bounded response size;
- strict JSON decoding;
- no prompt or provider response logging by default.

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

