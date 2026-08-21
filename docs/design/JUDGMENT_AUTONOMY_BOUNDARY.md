# ADR - Judgment, Autonomy and Adaptive Decision Boundary

Status: Accepted / Design - Not Implemented

## Decision

Judgment means deliberation among already-permitted possibilities. It may rank,
recommend, clarify, defer or abstain.

Judgment is not authority.

## Boundary

Judgment may evaluate:

- competing options;
- convenience;
- relevance;
- urgency;
- risk;
- confidence;
- context;
- approved preferences;
- learned pattern evidence.

Judgment must never:

- bypass policy;
- bypass confirmation;
- grant itself permissions;
- call Planner;
- call Runtime;
- call Drivers;
- create `Command`;
- mutate `DeviceState`;
- redefine safety priorities.

## Autonomy Levels

Conceptual autonomy levels:

- Level 0 - Deterministic: explicit commands or rules only.
- Level 1 - Advisory: recommend or rank options.
- Level 2 - Adaptive Advisory: use context, memory and learned patterns for
  suggestions.
- Level 3 - Delegated: act only inside explicit, narrow, revocable delegation.
- Level 4 - Autonomous: rejected.

Delegation must be explicit, scoped, revocable, auditable and below policy.

## Priority Rules

Non-learnable guardrails include:

- safety over convenience;
- privacy over personalization;
- explicit user instruction over inferred preference;
- policy over learned habit;
- confirmed current state over stale memory;
- clarify or abstain over unsafe assumption;
- user correction over inferred pattern.

User preferences may tune low-risk behavior, but cannot weaken safety, policy or
confirmation.

## Fuzzy Logic

Fuzzy logic may later support scoring, such as suitability to suggest or
interruption cost. It must never become authorization, policy or a sole safety
control.

## Explainability

Judgment should be able to explain the main signals, preference, confidence and
uncertainty behind a recommendation or abstention.

## Future Implementation Direction

The first judgment implementation should be fake, deterministic, in-memory,
recommendation-only, and must not execute anything.
