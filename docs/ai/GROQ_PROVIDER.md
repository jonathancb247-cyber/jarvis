# Groq Provider

Status: Experimental / Cloud Strict Structured Provider

JarvisOS includes an optional Groq provider for validating a real cloud AI path
through the existing AI Adapter boundary.

The provider is not wired into the default runtime, Runtime API, Dashboard, or
`ai_local`. It is started only through the explicit cloud AI entry point.

## Boundary

```text
Spanish user request
-> AI Adapter
-> AISafeContext
-> GroqAIProvider
-> strict Structured Output
-> existing normalization
-> strict JarvisOS validation
-> policy / confirmation
-> canonical command text
-> Planner
-> Runtime
```

Groq constrained decoding is not trusted by itself. Every provider result still
passes JarvisOS structural, semantic, policy, Planner, command-safety and
confirmation validation.

## Model

The first approved validation model is:

```text
openai/gpt-oss-20b
```

Other Groq models are not enabled by default in Phase 10.7. Model availability
and account limits must be rechecked before manual validation.

## Secrets

The provider reads the API key only from `GROQ_API_KEY` or receives it through
explicit constructor injection in tests/composition code.

The key must never be stored in:

- RuntimeProfile;
- device configuration;
- State Store;
- repository files;
- committed `.env` files;
- command-line arguments;
- Dashboard or browser code;
- logs, diagnostics, exceptions, tests or reports.

## Transport

The provider uses the official Groq HTTPS endpoint with TLS verification, a
fixed API path, strict timeouts and bounded responses. It does not use
streaming, retries, redirects, fallback providers, arbitrary endpoints, or
provider SDKs.

CI uses fake injected transports only. No Groq account, Internet access or real
API key is required for tests.

## Privacy

Groq may receive only the sanitized user request, safe device projections,
formal capabilities, safe semantic state, grammar and policy context.

JarvisOS does not send bindings, IP addresses, URLs, credentials, raw driver
payloads, State Store paths, RuntimeContext, EventBus, diagnostics, trust
internals, discovery candidates, arbitrary metadata, or persistent chat history.

## Errors

Provider failures are normalized into safe AI-layer errors such as:

- `ai_provider_unavailable`
- `ai_provider_timeout`
- `ai_provider_unauthorized`
- `ai_provider_rate_limited`
- `ai_model_not_found`
- `ai_model_unavailable`
- `ai_response_invalid`
- `ai_response_too_large`
- `ai_provider_protocol_error`

Raw provider responses, schema errors, request bodies, authorization headers,
endpoints, stack traces and exception representations are not exposed.
