# Gemini Provider

Status: Experimental / Not Real-Validated

Phase 10.9 adds an optional Gemini cloud provider behind the existing AI
Adapter boundary. It is not wired into the default Runtime, Runtime API or
Dashboard.

## Verified API Decisions

The implementation was checked against current official Google Gemini API
documentation before coding:

- API surface: Interactions API.
- Endpoint host: `generativelanguage.googleapis.com`.
- Endpoint path: `/v1/interactions`.
- API key header: `x-goog-api-key`.
- Structured output request: `response_format` with
  `mime_type: application/json` and a JSON `schema`.
- Output cap: `generation_config.max_output_tokens`.
- First validation model: `gemini-3.6-flash`.

The model allowlist is intentionally narrow and must be reverified before real
manual validation. Free-tier limits are account, project, tier and model
dependent and must not be treated as product guarantees.

## Boundary

```text
Spanish user request
-> AI Adapter
-> AISafeContext
-> GeminiAIProvider
-> structured output
-> existing AIActionPlan normalization
-> strict JarvisOS validation
-> policy / confirmation
-> canonical command text
-> Planner
-> Runtime
```

Gemini output remains untrusted. Provider-side schema guidance does not replace
JarvisOS validation.

The provider must not construct `Command`, call Planner, call Runtime, call
Drivers, mutate DeviceRegistry, write State Store, perform confirmation,
persist memory, retry automatically or fall back to another provider.

## Secret Boundary

The provider reads a key only from `GEMINI_API_KEY` at the explicit cloud-AI
composition root.

The key must never be placed in:

- RuntimeProfile;
- device configuration;
- DeviceState;
- State Store;
- repository files;
- `.env` files committed to Git;
- CLI arguments;
- Dashboard or browser code;
- logs, diagnostics or exception messages.

Tests use fake keys only.

## Transport

The Gemini transport uses synchronous Python standard-library HTTPS with
certificate and hostname verification enabled. It has:

- fixed official host and path;
- no arbitrary base URL;
- no HTTP fallback;
- no redirects;
- strict timeout;
- bounded request and response sizes;
- strict UTF-8 and JSON decoding;
- no streaming;
- no retry.

On Windows, the provider transport may create its TLS context through the
native OS certificate store via `truststore`. This keeps certificate and
hostname verification enabled while respecting the host's Windows trust policy.
JarvisOS does not disable antivirus HTTPS inspection, bypass TLS verification,
use `verify=False`, bundle certificates, or mutate Python's global SSL module.

Device HTTP drivers are not reused for provider traffic.

## Schema Strategy

Gemini receives the full provider-neutral `AIActionPlan` schema first:

- `AIActionPlan`;
- `AIActionStep`;
- `AIClarification`;
- `AIRefusal`.

The schema uses required fields, closed objects, bounded arrays, enums and
nullable clarification/refusal branches where supported by Gemini schema
semantics. JarvisOS still performs the authoritative structural, semantic,
policy and confirmation validation after decoding.

No Gemini-specific DTO exists in this phase.

## Privacy

Gemini may receive only sanitized AI context:

- Spanish user request;
- safe device ID/name/type;
- formal capabilities;
- safe parameter descriptors;
- semantic DeviceState;
- canonical command grammar;
- safety and confirmation policy.

Gemini must not receive bindings, URLs, IPs, credentials, raw HTTP payloads,
DriverResult, RuntimeContext, EventBus, State Store paths, diagnostics,
discovery candidates, trust internals or persistent conversation history.

## Entry Point

Future manual validation uses:

```powershell
$env:GEMINI_API_KEY = "<loaded locally>"
python -m jarvis_core.ai_cloud `
  --config profiles/http-lab.local.json `
  --provider gemini `
  --model gemini-3.6-flash
```

The API key is never accepted as a command-line argument.

## Current Status

Phase 10.9 does not perform a real Gemini call. Real validation remains gated by
`GEMINI_AI_VALIDATION_REQUIRED`.
