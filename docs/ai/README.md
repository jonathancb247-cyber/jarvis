# JarvisOS AI Adapter

Status: Experimental / Fake Adapter plus Validated Gemini Provider

JarvisOS currently includes a deterministic fake AI Adapter for validating the
AI boundary without a real model. It also includes an optional experimental
Gemini provider implementation that passed Phase 10.9 real-provider validation.

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

Implemented for Phase 10.9:

- optional Gemini provider boundary;
- fixed official Gemini HTTPS transport;
- full `AIActionPlan` structured-output schema mapping;
- explicit `GEMINI_API_KEY` injection at the AI-cloud composition root;
- fake-transport tests for CI;
- real-provider validation with `gemini-3.6-flash` outside CI.

Minimal safe-interaction increment (`jarvis_core/ai/interaction.py`):

- recognizes a small whitelist of *pure* greetings (`hola`, `hola jarvis`,
  `buenos días`, and justified variants) deterministically;
- normalizes case, accents, outer whitespace/punctuation and interior
  separators without removing significant content, and never intercepts a
  quoted greeting;
- answers a pure greeting as a `conversation` result without calling any
  provider;
- delegates every other message, including greetings accompanied by an
  instruction, verbatim to the existing `decide_understanding()` boundary;
- returns an `InteractionResult` with `schema_version`, `type`, `response_text`,
  `decision` and `commands_executed=false`, and exposes a JSON-safe
  `describe_interaction()` projection;
- never imports or calls Runtime, Drivers, the Planner, the resolver, the
  ExecutionGate, confirmation, or any provider, and never constructs or
  dispatches commands. An `executable_candidate` decision remains only a
  candidate that would still require the normal confirmation/policy path.
- this increment does not change the `/generate` contract or Companion
  behavior; the Android macro that currently calls `/generate` is not modified.

Not implemented:

- production-approved AI providers;
- OpenAI, Ollama, Claude, Mistral, Llama, Gemma, or other provider adapters;
- provider credentials in repository/config/state;
- real provider calls in CI;
- automatic provider fallback;
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
- [Gemini Provider](GEMINI_PROVIDER.md)
- [Gemini Validation](GEMINI_VALIDATION.md)
- [AI Provider Strategy](../design/AI_PROVIDER_STRATEGY.md)
