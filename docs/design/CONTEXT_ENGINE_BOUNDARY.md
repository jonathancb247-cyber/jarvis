# ADR - Context Engine Boundary

Status: Accepted / Design - Not Implemented

## Decision

Context answers:

```text
What appears to be happening now?
```

Context does not answer:

```text
What should Jarvis do?
```

The Context Engine may later aggregate bounded evidence into hypotheses with
confidence, freshness, provenance and uncertainty.

## Taxonomy

Context categories may include:

- temporal context;
- location context;
- activity context;
- device or environment context;
- social or communication context;
- session context;
- user availability;
- explicit mode context;
- inferred context;
- safety-relevant context.

## Evidence Rules

Context evidence may later come from approved signals such as time, explicit
modes, semantic `DeviceState`, active session state, approved local sensors or
approved external integrations.

Each signal should preserve freshness, provenance, sensitivity, confidence,
availability and explicit/inferred status.

## Explicit vs Inferred

Explicit context generally outranks inference. User correction dominates weak
sensor fusion or learned habits.

Examples:

- explicit Deep Focus outranks weak inactivity;
- "I am done studying" overrides inferred study context.

## Fusion And Contradictions

Multiple weak signals may support a hypothesis, but no weak single signal should
prove high-stakes context. Contradictions must reduce confidence or expire the
hypothesis.

## Boundary

Context must never:

- recommend actions;
- activate scenes automatically;
- call Planner;
- call Runtime;
- call Drivers;
- create `Command`;
- mutate `DeviceState` as inference;
- create Memory;
- change policy;
- bypass confirmation.

Context is ephemeral by default. Persistent context requires a future ADR.

## Prohibited Behavior

This ADR rejects unrestricted sensor collection, continuous surveillance,
persistent raw sensor history, raw audio context storage, provider-owned context
and AI-required context detection.

## Future Implementation Direction

The first Context Engine implementation should be fake, deterministic,
in-memory, and limited to explicit signals such as time and mode.
