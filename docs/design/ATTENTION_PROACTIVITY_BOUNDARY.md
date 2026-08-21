# ADR - Attention / Proactivity Boundary

Status: Accepted / Design - Not Implemented

## Decision

Attention answers:

```text
Should Jarvis interrupt or surface this now, and how?
```

Attention does not decide whether an action is permitted and does not execute
physical actions.

## Ownership

Attention may own:

- whether to surface something;
- timing;
- interruption priority;
- deferral;
- escalation;
- output surface selection;
- notification budget;
- quiet periods;
- cooldown or suppression behavior;
- interruption explanation.

Attention must never own:

- execution permission;
- Runtime;
- Planner;
- Driver calls;
- `DeviceState` mutation;
- memory writes;
- policy mutation;
- confirmation bypass;
- autonomous delegation.

## Priority And Interruption

Attention may distinguish safety-critical, urgent, important, normal,
informational and low-value surfacing classes.

It may estimate interruption cost from context such as driving, Deep Focus,
sleep, conversation, work, exercise, active media and recent interruptions.

Safety-critical attention requires deterministic and policy-backed future
design. It must not depend solely on fuzzy logic or AI.

## Quiet Modes And Budgets

Future attention behavior may include quiet windows, do-not-disturb states,
cooldowns, batching, repeated-topic suppression and bounded escalation.

JarvisOS should minimize unnecessary interruption while maximizing useful,
timely assistance. It must not optimize for engagement, screen time, response
rate, emotional dependency or advertising-style nudging.

## Surface Selection

Future surfaces may include room speaker, phone, watch, Dashboard, vehicle,
local notification or silent visual cue. Selection must consider context,
urgency, privacy, availability, sensitivity and disruption cost.

Sensitive information should prefer private surfaces.

## Relationship To Execution

Attention may surface a suggestion or alert. Any physical action still requires:

```text
Policy
-> Confirmation if required
-> Planner
-> Runtime
```

There is no Attention -> Runtime path.

## Future Implementation Direction

The first attention implementation should be fake, deterministic, in-memory,
recommendation-only, and limited to quiet-window, priority and deferral tests.
