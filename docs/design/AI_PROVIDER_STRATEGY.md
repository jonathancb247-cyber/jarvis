# ADR - AI Provider Strategy Consolidation After Gemini Validation

Status: Accepted / Architecture Strategy - Not Implementation

## Context

JarvisOS now has one real structured-planning provider validation:
Gemini passed Phase 10.9 through the existing AI Adapter boundary. Gemini remains
optional, explicit, experimental, non-default and not production-approved.

Earlier provider drafts remain useful as research but are not merge-ready:

- PR #38 contains Ollama local-provider work.
- PR #39 contains Groq strict structured-provider work.

Those drafts were created before Gemini validation and before later voice
architecture work clarified separate planning, local AI, speech and realtime
lanes. They must not be merged as-is.

## Decision

JarvisOS separates AI provider strategy into three lanes:

1. Structured Planning Provider
2. Local Essential AI
3. Voice / STT / Realtime Provider Lane

The lanes share one invariant: provider output is never trusted as executable
authority. JarvisOS validation, policy, confirmation, Planner parsing and Runtime
ownership remain authoritative.

## Lane 1 - Structured Planning Provider

Gemini is the current validated experimental structured-planning provider.

Approved role:

- optional explicit cloud provider;
- structured output through the existing AI Adapter;
- full provider-neutral `AIActionPlan` first;
- strict JarvisOS validation after provider output;
- no default Runtime wiring;
- no Dashboard AI wiring;
- no automatic fallback.

Gemini validation is evidence, not permanent provider selection. Future Gemini
work must still reverify model availability, account quota, transport behavior
and schema compatibility before new real-provider claims.

## Lane 2 - Local Essential AI

Ollama remains a future local-provider candidate, not a validated provider.

PR #38 classification: REFERENCE / REDESIGN.

Useful lessons to preserve:

- localhost-only local endpoint boundary;
- explicit `ai_local` entry point;
- no credentials;
- bounded requests and responses;
- safe diagnostics;
- malformed-output tests;
- wrapper-response tests;
- no streaming for initial validation.

PR #38 should not be merged as-is. A future Ollama gate must choose a current
model, verify local hardware capacity, validate structured output against the
current `AIActionPlan` contract, and prove deterministic plus real local
behavior before any merge.

## Lane 3 - Voice / STT / Realtime Provider Lane

Groq's most useful near-term role is voice and low-latency interaction research,
not strict full-plan generation.

PR #39 classification: RESEARCH / DO NOT MERGE AS VALIDATED PROVIDER.

Useful lessons to preserve:

- fixed provider endpoint;
- explicit static User-Agent;
- secure TLS and hostname verification;
- Windows trust-store compatibility through explicit SSL context;
- no global SSL monkey patching;
- no redirects;
- bounded request and response handling;
- safe HTTP status normalization;
- fake transport and security tests.

Groq STT work belongs to the voice provider lane and must remain separate from
Groq structured-planning work. Future Groq chat, tool/function calling or
realtime voice work requires a separate design gate. Groq strict full
`AIActionPlan` generation should not continue without new provider evidence.

## Explicit Non-Decisions

This ADR does not approve:

- provider registry;
- provider router;
- service locator;
- automatic provider fallback;
- automatic model switching;
- cloud provider as default;
- provider-owned execution;
- provider-specific Runtime branching;
- provider-specific Planner behavior;
- direct provider-to-Command construction;
- direct provider-to-Driver calls;
- implicit cloud escalation;
- background provider health polling;
- merging PR #38 or PR #39.

## Provider Selection Ownership

Provider selection belongs at explicit composition and entry points, such as
AI-cloud or future AI-local commands.

Provider selection must not be owned by:

- Runtime;
- Planner;
- Drivers;
- DeviceState;
- State Store;
- Runtime API;
- Dashboard;
- device configuration.

## Failure Semantics

Provider failure must fail safe:

- no fabricated plan;
- no partial execution;
- no fallback unless a future ADR explicitly approves it;
- no DeviceState mutation;
- no Runtime execution;
- no raw provider payload, prompt, key, header or stack trace exposure.

Provider-specific failures may be normalized into existing safe AI Adapter
results, but they do not become device state or policy truth.

## Relationship To Gemini

Gemini remains the first real structured-planning provider validated by
JarvisOS, but it is still experimental.

Gemini must remain:

- optional;
- explicit;
- non-default;
- subject to current account quota and model availability;
- behind the AI Adapter;
- constrained by `AIActionPlan` validation, policy, confirmation, Planner and
  Runtime.

Gemini must not become:

- production-approved by implication;
- a permanent provider choice;
- a fallback target;
- a Dashboard feature;
- a Runtime dependency.

## Relationship To Ollama

Ollama remains valuable for local privacy, offline use and Local Essential AI.
The current PR #38 work is historical reference, not validated implementation.

A future Ollama design or implementation phase should start from current main
and reuse only lessons that still fit the boundary.

## Relationship To Groq

Groq remains valuable for low-latency provider research, especially voice/STT or
future tool/function-calling designs. PR #39 preserves important transport and
security findings but did not validate strict full-plan generation.

Groq STT validation in voice phases must not be treated as structured-planning
validation.

## Draft PR Disposition

After this ADR is merged and recorded, PR #38 and PR #39 may be closed as
superseded research references if their useful lessons are preserved in docs.

The branches do not need to be deleted immediately. They may remain available
for historical inspection until a later cleanup pass.

## Future Ollama Re-Entry Gate

A future Ollama phase must:

- select a current candidate model;
- verify host hardware capacity;
- use current AI Adapter contracts;
- validate structured output with fake and real local tests;
- keep default Runtime AI-free;
- avoid provider fallback;
- preserve safe diagnostics and bounded transport.

## Future Groq Re-Entry Gate

A future Groq phase must pick one clear role:

- voice/STT;
- chat;
- tool/function calling;
- realtime voice;
- or renewed structured planning with new evidence.

Each role needs its own design gate. Groq strict full-plan generation should not
be retried as a local patch exercise without upstream capability evidence.

## Consequences

This consolidation reduces provider confusion:

- Gemini carries the current structured-planning evidence.
- Ollama remains the local AI candidate.
- Groq remains a voice and low-latency research candidate.
- Draft provider PRs are preserved as research instead of merged into current
  architecture.

The tradeoff is that JarvisOS keeps multiple experimental directions alive
without automatic fallback or a provider registry. That is intentional until
real provider behavior justifies a broader orchestration design.

## Deferred Decisions

Separate design gates remain required for:

- Ollama local-provider re-entry;
- Groq voice/STT validation;
- Groq tool/function calling;
- realtime cloud voice privacy;
- persistent secrets management;
- provider registry or fallback, if ever needed.
