# JarvisOS Architecture Guardrails

Status: Current
Purpose: Permanent architectural invariants for humans and coding agents.

This document defines boundaries that should not be crossed casually.
It is not a roadmap and does not define implementation phases.

## 1. Core Principle

JarvisOS is a modular runtime for physical and digital agents.

The core must remain stable while transports, AI providers, hardware,
interfaces, and integrations remain replaceable.

## 2. Runtime Boundary

- Runtime owns execution.
- Runtime must remain transport-neutral.
- Runtime must not contain HTTP, MQTT, BLE, Zigbee, Matter, UI, or AI-provider logic.
- New transports must not create Runtime branching.
- Transport-specific behavior belongs behind adapters/drivers.

## 3. Command and Planner Boundary

- Canonical commands are the authoritative execution language.
- Planner behavior remains deterministic.
- AI providers must not construct or execute Runtime Command objects directly.
- Natural language must pass through approved structured boundaries before execution.
- Free-form model output must never directly trigger physical mutations.

## 4. AI Boundary

AI may:

- interpret user intent;
- produce approved structured plans;
- converse;
- explain;
- suggest.

AI does not:

- own Runtime;
- bypass policy;
- bypass confirmation;
- directly mutate DeviceState;
- receive transport secrets;
- receive unnecessary broker/topic/device internals.

AI provider availability must not determine whether the core Runtime can start.

## 5. Driver Boundary

Drivers:

- translate semantic device operations into transport-specific operations;
- return bounded semantic DriverResult values;
- may use HTTP, MQTT, or future transports internally.

Drivers must not:

- own policy;
- own authorization;
- mutate DeviceState directly;
- expose raw transport exceptions upward;
- introduce transport branching into Runtime or Router.

## 6. DeviceState Boundary

DeviceState represents semantic knowledge about a device.

It is not:

- transport connectivity;
- broker state;
- socket state;
- HTTP status;
- raw driver diagnostics.

State meanings:

- unknown: no trustworthy semantic state is known;
- known: semantic state was successfully observed or confirmed and is current;
- stale: prior semantic state exists but is not confirmed current.

Transport connectivity alone never implies known/current state.

Failure must not invent semantic state.

## 7. Persistence Boundary

Persistence stores approved semantic state.

Restored state does not prove current physical availability.

After restart, previously known device state may be restored as stale until
an explicit successful observation establishes current state again.

Technical transport errors and secrets must not become persisted semantic state.

## 8. API and Dashboard Boundary

API and Dashboard consume safe projections of JarvisOS state.

They must not become alternative execution architectures.

They must not expose:

- secrets;
- credentials;
- raw transport exceptions;
- internal broker details unnecessarily;
- AI-provider internals.

Dashboard behavior must remain downstream of the same Runtime and policy used by
other interfaces.

## 9. Device Interoperability

JarvisOS follows:

- Protocol over ecosystem.
- Capability over brand.
- Capability over age.

A supported protocol does not automatically imply a trusted device.

Discovery != Identification.
Identification != Compatibility.
Compatibility != Trust.
Trust != Authorization.

## 10. Security

- Secrets do not belong in source control.
- Secrets do not belong in normal Runtime profiles.
- LAN/public exposure requires explicit security design.
- Anonymous local-lab access must never silently become production policy.
- Mutations remain subject to existing authorization and confirmation policy.
- Remote access must not expose Runtime directly by convenience.

## 11. Optional Infrastructure

JarvisOS must degrade gracefully when optional infrastructure is unavailable.

Examples include:

- AI providers;
- cloud services;
- remote connectivity;
- dashboards;
- external brokers when not required by the active profile.

Optional adapters must remain replaceable.

## 12. Architectural Change Rule

A change that violates one of these guardrails is not a normal implementation
detail.

It requires explicit architectural review and, when appropriate, an ADR.

Do not silently weaken a guardrail to make a feature easier to implement.