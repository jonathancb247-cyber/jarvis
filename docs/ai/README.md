# JarvisOS AI Adapter

Status: Experimental / Fake and Optional Cloud Provider

JarvisOS currently includes a deterministic fake AI Adapter for validating the
AI boundary without a real model. It also includes an optional Groq cloud
provider for strict Structured Output validation.

The adapter is not wired into the default runtime. `python -m jarvis_core`
remains AI-free, offline-safe, and deterministic.

## Current Scope

Implemented for Phase 10.3:

- immutable adapter-layer contracts;
- deterministic fake provider;
- safe-context projection;
- strict plan validation;
- command safety checks;
- Planner-based command validation;
- read/mutation classification;
- adapter-local confirmation state;
- clarification and refusal handling;
- bounded sequential execution through the Runtime-owned adapter boundary.

Implemented for Phase 10.7:

- internal provider abstraction;
- Groq provider configuration;
- strict AIActionPlan JSON Schema for Groq Structured Outputs;
- standard-library HTTPS transport with fake transport support in CI;
- explicit `python -m jarvis_core.ai_cloud` entry point;
- safe secret injection through `GROQ_API_KEY`;
- normalized provider, authorization and rate-limit errors.

Not implemented:

- default runtime AI wiring;
- Dashboard AI chat;
- OpenAI, Ollama, Claude, Mistral, Llama, Gemma, or provider registry routing;
- stored provider credentials;
- streaming;
- persistent AI memory;
- embeddings, RAG, or vector databases;
- voice, vision, dashboard, or autonomous workflows.

## Boundary

```text
User request
-> Fake AI Provider
-> AIActionPlan
-> validation and policy checks
-> canonical command text
-> Runtime-owned Adapter Boundary
-> Planner
-> Command
-> Runtime
-> CapabilityResult
-> sanitized AI adapter result
```

The fake provider never creates `Command`. The AI Adapter never calls drivers,
mutates `DeviceRegistry`, writes State Store, or bypasses Runtime.

Cloud AI flow:

```text
Spanish user request
-> AI Adapter
-> AISafeContext
-> GroqAIProvider
-> strict Structured Output
-> existing validation
-> canonical command text
-> Runtime-owned Adapter Boundary
```

Provider-side constrained decoding does not replace JarvisOS validation.

## Documents

- [Structured Plan](STRUCTURED_PLAN.md)
- [Safe Context](SAFE_CONTEXT.md)
- [Fake AI Adapter](FAKE_AI_ADAPTER.md)
- [Groq Provider](GROQ_PROVIDER.md)
- [Cloud AI Validation](CLOUD_AI_VALIDATION.md)
