# ADR - Cognitive Signal / Evidence Vocabulary

Status: Accepted / Design - Not Implemented

## Decision

JarvisOS cognitive components should share vocabulary for evidence without
sharing ownership, storage, authority or implementation models.

Shared vocabulary is not shared cognitive state.

The vocabulary must not become policy, permission, execution authority, a
universal cognitive database, a provider schema or a giant base class.

## Canonical Cognitive Flow

The accepted cognitive flow is:

```text
Events / DeviceState / explicit modes
-> Context

Historical observations / feedback
-> Learning

Approved facts / preferences / experiences
-> Memory

Context + Learning + Memory + policy constraints
-> Judgment

Judgment
-> Attention / Policy / Confirmation

Only accepted deterministic flow
-> Planner / Runtime
```

No cognitive component may call Runtime, call Drivers, mutate `DeviceState`,
bypass confirmation or grant itself authority.

## Minimal Vocabulary

The first shared vocabulary should cover:

- evidence kind;
- confidence;
- freshness;
- provenance;
- explicit vs inferred;
- sensitivity;
- user scope;
- timestamps and expiration;
- urgency;
- risk or severity;
- relevance;
- contradiction;
- safe explanation evidence.

## Evidence Kinds

Conceptual evidence kinds include:

- fact;
- observation;
- signal;
- hypothesis;
- inference;
- preference;
- pattern;
- recommendation;
- decision;
- evidence reference.

## Confidence

Confidence means how strongly a component trusts evidence for its purpose.

Confidence is not probability unless explicitly modeled as such. Confidence is
not authority. High confidence cannot bypass policy or confirmation.

Conceptual bands may include unknown, low, medium, high and explicit/certain
where appropriate. Numeric thresholds are not approved.

## Freshness And Expiration

Shared freshness terms may include fresh, aging, stale and expired.

This vocabulary does not replace `DeviceState` semantics. Expired evidence
should not influence current decisions. Stale evidence may be useful only with
caveats.

## Provenance

Evidence should conceptually describe source, such as explicit user input,
`DeviceState`, local sensor, external integration, Memory, Learning, Context,
AI-assisted inference or system rule.

Provenance supports trust, conflict handling, privacy and explanation.

## Sensitivity And User Scope

Sensitivity categories may include ordinary, personal, sensitive and restricted.
User scope may include system, household, specific user, guest/session and
unknown.

Unknown identity must not inherit personal Memory or Learning. Derived evidence
must not silently become less sensitive than its inputs.

## Distinctions

Keep these concepts separate:

- fuzzy membership is not confidence;
- confidence is not authority;
- urgency is not risk;
- relevance is not importance;
- recommendation strength is not permission;
- AI self-reported confidence is not trusted cognitive confidence.

AI-derived evidence must preserve AI-assisted provenance.

## Contradiction And Explanation

Evidence may reference supporting and contradicting evidence. The vocabulary
does not resolve conflicts.

Safe explanation evidence should support short explanations without exposing
secrets, raw provider traces, prompts, raw sensor streams, private history or
transport internals.

## Implementation Shape

Reject a universal `CognitiveEvidence` base model for now.

Prefer:

- documentation terminology first;
- component-owned models;
- composition;
- tiny neutral value objects later only if implementation needs them.

## Future Implementation Direction

The first deterministic cognitive vertical slice should use only the minimal
vocabulary needed for fake in-memory recommendation scenarios.
