# ADR - Second Brain / Memory Boundary

Status: Accepted / Design - Not Implemented

## Decision

JarvisOS may later include a Second Brain / Memory subsystem for approved and
remembered knowledge. Memory is not execution authority.

Memory may store future concepts such as:

- rules and preferences;
- facts and memories;
- experiences;
- derived summaries;
- expiring memories.

These are conceptual categories, not storage types or schemas.

## Boundary

Second Brain / Memory is separate from:

- `DeviceState`, which represents semantic state of physical or digital devices;
- `RuntimeProfile`, which is declarative configuration;
- State Store, which persists semantic `DeviceState`;
- Conversation Session, which is short-lived turn context;
- `AISafeContext`, which is a filtered provider-facing snapshot.

State Store must not become Second Brain storage.

## Write Rules

Memory may enter the system through:

- explicit user save requests;
- user-approved suggestions to save;
- approved summaries;
- corrections;
- expiring temporary memory when explicitly designed.

Silent persistent memory is not approved.

## Recall Rules

Recalled memory is evidence only. It must not:

- create `Command`;
- call Planner;
- call Runtime;
- call Drivers;
- mutate `DeviceState`;
- bypass confirmation;
- authorize execution.

## Consent And Privacy

Persistent memory requires explicit consent and must support provenance,
inspection, deletion, correction and expiration.

Memory must not store:

- credentials or secrets;
- raw audio;
- raw transcripts by default;
- unrestricted private messages;
- provider prompts or responses;
- raw transport diagnostics.

Sensitive memory requires a future sensitive-data and identity design.

## Provider Boundary

AI providers may later help summarize low-risk content, but providers must not
own persistent memory, write directly to memory, or receive unrestricted memory
dumps.

## Non-Decisions

This ADR does not select:

- database technology;
- vector database;
- embeddings provider;
- cloud sync;
- cross-device sync;
- memory UI;
- memory persistence schema.

## Future Implementation Direction

The first memory implementation, when opened, should be fake, deterministic,
in-memory, recommendation-only where applicable, and independent of Runtime
execution.
