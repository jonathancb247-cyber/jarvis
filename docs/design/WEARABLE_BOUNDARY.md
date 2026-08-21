# ADR - Wearable Boundary: Wear OS Presence / Connection Signal

Status: Accepted / Design - Not Implemented

## Context

JarvisOS may eventually use wearables as personal context sources,
interaction clients, notification surfaces, voice surfaces, or control
surfaces. A wearable is not automatically any of those things.

The first wearable boundary must preserve current JarvisOS rules:

- Runtime owns execution.
- Planner remains deterministic.
- Drivers translate semantic device operations.
- `DeviceState` remains the semantic state of devices.
- Cognitive components consume detached evidence and do not execute.
- Voice remains an interface to JarvisOS, not a second execution pipeline.

## Decision

JarvisOS will introduce a future Wearable Boundary before any Wear OS,
Pixel Watch, Xiaomi Watch S3, health-signal, notification, voice, or control
work enters the product.

The first approved wearable role is:

```text
Wearable Presence / Connection Context Source
```

The only approved first signal is:

```text
watch_connected
```

`watch_connected` means:

```text
A known wearable client/probe currently appears connected to the local
wearable boundary.
```

It does not mean user presence, watch wearing, identity proof, wakefulness,
availability, health status, or location.

## Wearable Boundary Ownership

The Wearable Boundary may own:

- wearable client or probe registration;
- connection and status observation;
- wearable role and capability declaration;
- capability degradation status;
- normalized detached read-only semantic projection;
- provenance, freshness, confidence, sensitivity and user-scope metadata;
- safe diagnostic explanation.

The Wearable Boundary must not own:

- Runtime;
- Planner;
- Drivers;
- `Command` creation;
- execution;
- policy or confirmation;
- `DeviceState` mutation or refresh;
- cognitive decisions;
- notification delivery;
- voice authority;
- identity or authentication proof;
- persistence by default.

## Wearable Roles

Wearable roles are independent. A wearable may support some, all, or none.

Conceptual roles include:

- presence or context source;
- sensor source;
- interaction client;
- notification surface;
- voice surface;
- control surface;
- identity or authentication signal.

Role support must be explicit. Role support in one category never implies
support in another.

## Pixel Watch / Wear OS

Pixel Watch / Wear OS is the first implementation target.

The first approved role is only:

- Presence / Connection Context Source.

Not approved yet:

- heart rate;
- HRV;
- sleep;
- exercise;
- microphone;
- speaker;
- haptics;
- notifications;
- quick replies;
- controls;
- identity proof;
- location;
- health inference.

## Xiaomi Watch S3

Xiaomi Watch S3 is classified as:

```text
Closed-Device Research / Graceful Degradation Reference
```

JarvisOS may use it conceptually to validate:

- `blocked_by_platform`;
- `requires_companion`;
- `unknown`;
- `partially_supported`.

This ADR does not claim:

- control;
- raw sensor access;
- reliable SPP;
- audio routing;
- notifications;
- reverse-engineering success.

## Wearable Capability And Degradation Model

Wearable capability status is separate from executable `DeviceCapability`.

Initial status values:

- `supported`
- `partially_supported`
- `unavailable`
- `blocked_by_platform`
- `requires_companion`
- `requires_permission`
- `unknown`

Conceptual metadata may include:

- role;
- source;
- permission requirement;
- sensitivity;
- freshness;
- confidence;
- user scope;
- user-safe reason or details.

This is separate from `DeviceCapability` because wearable capability status
describes evidence availability and platform constraints, not
Runtime-executable device actions.

## `watch_connected` Semantics

Allowed conceptual states:

- `connected`
- `disconnected`
- `unknown`
- `stale`

Recommended metadata:

- provenance: wearable;
- freshness: fresh, stale or unknown;
- confidence: medium for connected/disconnected and low for unknown;
- sensitivity: personal;
- user scope: configured user association or unknown/session.

Disconnected does not mean:

- user absent;
- watch unworn;
- user unreachable.

Unknown does not mean disconnected.

Configured watch association is not authentication proof.

## Connection Source Model

The future source is conceptual:

```text
Wear OS local app/probe
-> Wearable Boundary
-> connection semantic projection
```

The connection signal may later originate from an app session, local transport,
companion-observed connection or another explicit probe. The implementation
phase must state which source is used and exactly what that source proves.

This ADR does not select concrete Android or Wear OS APIs.

## Cognitive Integration

Future flow:

```text
Wear OS probe/client
-> Wearable Boundary
-> detached wearable semantic projection
-> Cognitive Signal
-> Context
-> Judgment
-> Attention
-> local diagnostic report
```

Never:

```text
Wearable signal
-> Runtime action
```

Initial cognitive behavior should be diagnostic only:

- connected: watch connection signal is currently available;
- disconnected/stale/unknown: wearable signal unavailable or stale, context
  confidence reduced.

No action, no notification delivery and no device refresh occurs.

## Context Interpretation

`watch_connected` may initially support only concepts equivalent to:

- `wearable_available`;
- `personal_surface_evidence_available`;
- `context_evidence_available`.

It must not support:

- `user_present`;
- `user_wearing_watch`;
- `user_awake`;
- `user_authenticated`.

## Attention Boundary

Future Attention may consume weak evidence that a personal watch surface may be
available.

Wearable Phase 1 must not deliver notifications.

The signal may influence only fake or local diagnostic Attention output until a
separate notification-delivery design is approved.

## Privacy And User Scope

Connection status is personal context.

Rules:

- local-only by default;
- no persistence by default;
- no provider or cloud exposure by default;
- no identity inference;
- no location inference;
- no behavioral profiling;
- configured watch association is not authentication proof.

Unknown identity must not inherit personal Memory or Learning.

## Failure Semantics

If the watch disconnects or the probe fails:

- Runtime continues;
- `DeviceState` is unaffected;
- cognition receives stale or unknown wearable evidence;
- no fabricated user context is created;
- no automatic fallback action occurs;
- no notification is delivered;
- diagnostic reports expose degraded wearable signal honestly.

## Fake CI Gate

Before real hardware validation, implementation must provide deterministic fake
fixtures for:

- connected;
- disconnected;
- unknown;
- stale.

Tests must prove:

- semantic mapping;
- cognitive mapping;
- degradation behavior;
- no Runtime, Planner or Driver imports;
- no `DeviceState` mutation;
- no `Command` construction;
- no persistence, network or hardware requirement in CI;
- no identity inference;
- no notification delivery.

## Real Validation Gate

Future real validation requires:

- authorized Pixel Watch probe or app;
- local connection observation;
- connect/disconnect sequence;
- cognitive diagnostic changes accordingly;
- no execution;
- no notifications;
- no health, location or voice data.

This ADR does not perform or authorize real validation.

## Sensitive Wearable Context

A separate future ADR or gate is required before these enter cognition:

- heart rate;
- HRV;
- sleep;
- exercise or activity;
- precise location;
- biometrics;
- wrist presence as identity proof.

That gate must define consent, local-only processing, retention limits,
default non-persistence, medical non-claims, sensitivity propagation and
identity limitations.

## Adaptive Wake

Adaptive Wake remains design-only.

Prerequisites:

- Sensitive Wearable Context ADR;
- validated sleep/wake evidence;
- explicit consent;
- retention policy;
- context contradiction handling;
- Attention escalation;
- hard alarm deadline;
- manual override;
- lighting and audio safety.

## Voice Boundary

Wearable voice remains future work.

Rules:

- no microphone or speaker assumption;
- capability-dependent only;
- no second execution pipeline;
- existing Voice architecture remains authoritative.

Wearable voice must still pass policy, confirmation, Planner and Runtime
boundaries when actions are involved.

## Explicit Non-Decisions

This ADR does not approve:

- HR, HRV or sleep;
- messaging or WhatsApp;
- notification delivery;
- watch UI;
- watch actions;
- device control;
- voice or audio;
- location;
- authentication;
- persistence;
- background surveillance;
- Xiaomi reverse engineering;
- provider or cloud dependence;
- wearable-triggered Runtime action.

## Future Implementation Direction

Recommended next phase:

```text
Wearable Phase 1 - Wear OS Presence / Connection Signal
```

Expected sequence:

1. fake deterministic fixtures;
2. tiny wearable status contract;
3. detached cognitive mapping;
4. local report only;
5. real Pixel Watch validation after the fake path passes.

Wearable Phase 1 must remain non-executing, non-persistent, local-first and
connection-signal only.
