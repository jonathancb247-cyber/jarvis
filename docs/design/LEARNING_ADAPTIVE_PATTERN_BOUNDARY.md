# ADR - Learning / Adaptive Pattern Boundary

Status: Accepted / Design - Not Implemented

## Decision

Learning may identify recurring patterns from bounded observations and user
feedback. Learning produces evidence and hypotheses, not authority.

## Taxonomy

Conceptual learning categories include:

- frequency pattern;
- temporal pattern;
- contextual pattern;
- preference hypothesis;
- routine or habit;
- anomaly baseline;
- adaptive threshold;
- feedback signal;
- correction or suppression signal.

These are conceptual classes, not schemas.

## Pattern Lifecycle

Patterns may move through:

```text
candidate
-> emerging
-> established
-> weakening
-> expired / rejected
```

High confidence never promotes a pattern into a rule automatically.

## Confidence And Decay

Learning may track observation count, consistency, recency, context match,
contradiction count, feedback and uncertainty.

Patterns should decay when contradicted, rejected, not observed, or made stale by
context changes.

## Promotion Boundary

Safe promotion flow:

```text
learned pattern
-> Judgment proposal
-> explicit user consent
-> approved preference or rule
```

Learning must never create delegation automatically.

## Prohibited Behavior

Learning must not:

- silently profile users;
- call Planner;
- call Runtime;
- call Drivers;
- create `Command`;
- mutate `DeviceState`;
- change policy;
- weaken confirmation;
- learn safety thresholds;
- learn policy thresholds;
- persist sensitive inference silently.

Learning may tune non-safety fuzzy inputs only after a future design.

## Future Implementation Direction

The first learning implementation should be fake, deterministic, in-memory,
bounded to simple counters or temporal patterns, and recommendation-only.
