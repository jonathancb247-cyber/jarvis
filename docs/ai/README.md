# JarvisOS AI Adapter

Status: Experimental / Deterministic Fake Only

JarvisOS currently includes a deterministic fake AI Adapter for validating the
AI boundary without a real model.

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

Not implemented:

- real AI providers;
- OpenAI, Ollama, Claude, Mistral, Llama, Gemma, or other provider adapters;
- provider credentials;
- provider network calls;
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

## Documents

- [Structured Plan](STRUCTURED_PLAN.md)
- [Safe Context](SAFE_CONTEXT.md)
- [Fake AI Adapter](FAKE_AI_ADAPTER.md)
