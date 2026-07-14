# Deterministic Fake AI Adapter

Status: Experimental / Deterministic Fake Only

The deterministic fake AI Adapter validates the AI boundary without using a real
AI provider.

It uses:

- no network;
- no credentials;
- no provider SDK;
- no model;
- no probabilistic output.

## Purpose

The fake adapter exists to test the contracts and boundaries approved for Epic
10 before any real provider is considered.

It validates:

- plan normalization;
- safe-context projection;
- command safety;
- deterministic Planner validation;
- read/mutation classification;
- confirmation gating;
- clarification;
- refusal;
- sequential execution;
- safe adapter results.

## Public Behavior

The adapter has separate proposal, confirmation, cancellation, and execution
behavior.

Mutating plans are proposed and stored as pending confirmation. They do not
execute until the exact normalized plan is confirmed.

Read-only plans may execute without confirmation only after deterministic
classification.

## Default Runtime

The fake adapter is not registered in the default runtime.

```bash
python -m jarvis_core
```

continues to start the normal AVP-001 runtime with no AI, no provider, no
credentials, no network, no demo devices, and no State Store.

## Testing

Automated tests use formal devices and fake drivers. No hardware is required.
No ESP32 validation is required for this phase.
