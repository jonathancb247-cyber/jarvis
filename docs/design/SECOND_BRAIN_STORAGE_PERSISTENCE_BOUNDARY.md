# ADR - Second Brain Storage / Persistence Boundary

Status: Accepted / Design - Not Implemented

## Context

Second Brain Phase 1 validates deterministic in-memory retrieval over seeded
approved knowledge. It proves retrieval semantics for provenance, freshness,
supersession, contradiction and local diagnostic output.

This ADR defines the boundary for a future durable-memory implementation. It
does not implement SQLite, create a database, create migrations, add connectors,
approve real personal memory storage or open Second Brain Phase 3.

## Decision

Second Brain durable persistence must remain separate from:

- `DeviceState`;
- State Store;
- `RuntimeProfile`;
- configuration;
- Conversation Session;
- Context;
- Runtime authority.

Persistence stores approved knowledge.
Persistence does not decide truth.
Persistence does not execute.
Persistence does not create authority.

Rejected flow:

```text
Second Brain storage
-> Runtime action
```

## Recommended First Backend

The recommended first durable backend for fixture-only validation is SQLite
through Python's standard-library `sqlite3`.

SQLite is recommended because it provides:

- transactions;
- correction and supersession atomicity;
- indexed structured queries;
- schema and version support;
- deterministic testing;
- a portable local file;
- no new dependency.

SQLite is a storage adapter choice, not a core JarvisOS dependency.

SQLite must not leak into:

- Runtime;
- Planner;
- Drivers;
- `DeviceState`;
- API;
- Dashboard;
- Cognition architecture generally.

## State Store Separation

`JsonDeviceStateStore` remains DeviceState-only. It must not become Second Brain
storage.

Second Brain must not reuse DeviceState persistence semantics as memory
semantics.

Reusable concepts from current DeviceState persistence may include:

- schema versioning;
- strict validation;
- bounded size and depth;
- safe errors;
- deterministic serialization;
- atomic and failure-safe write concepts.

The implementation boundary remains separate.

## Durable-Memory Eligibility

Potentially eligible later:

- explicit user-approved fact;
- explicit correction;
- approved preference;
- manually promoted knowledge item;
- source-backed project decision snapshot;
- source-reference metadata;
- explicitly authorized project or system snapshot.

Not automatically eligible:

- raw conversation history;
- transient Context;
- `DeviceState`;
- telemetry;
- learned patterns;
- AI or provider guesses;
- inferred personality;
- private messages;
- raw audio;
- raw transcripts;
- credentials or secrets.

## Write Authorization

Default: no silent durable writes.

Approved future write origins:

1. explicit "remember X" request;
2. explicit correction;
3. user-approved save suggestion;
4. trusted source-backed import through a future connector gate;
5. explicit project or system snapshot with source authority.

Each durable write conceptually requires:

- provenance;
- sensitivity;
- user scope;
- approval state;
- retention class;
- safe explanation.

No AI provider may commit durable memory directly.

## Durable Record Semantics

Future durable records should conceptually preserve:

- `knowledge_id`;
- `kind`;
- `topic`;
- `summary`;
- `source_type`;
- `source_reference`;
- `captured_at`;
- `observed_at`;
- `freshness`;
- `confidence`;
- `origin`;
- `sensitivity`;
- `user_scope`;
- `approval_state`;
- `retention_class`;
- `expires_at`;
- `supersedes`;
- `superseded_by`;
- `contradicted_by`;
- `revision`;
- `deleted_at`;
- purge state or tombstone semantics;
- `safe_explanation`.

This is not a SQL schema. Tables and columns are not finalized by this ADR.

## Correction And Supersession

Corrections are append-oriented:

```text
old fact/preference X
+
explicit correction Y
->
new record Y
+
X superseded by Y
```

Requirements:

- do not silently overwrite history;
- retrieval selects current Y;
- old X may remain inspectable as superseded historical evidence;
- correction and supersession must be atomic when persistence exists.

Sensitive deletion or purge is a separate exception.

## Delete And Forget Semantics

Second Brain must distinguish:

- supersession: historical replacement, where content may remain;
- logical delete: unavailable to normal retrieval;
- hard purge: personal or sensitive content actually removed.

"Forget this" must not merely hide content while it remains recallable.

Future implementation must distinguish:

- forget one item;
- forget topic or category;
- forget source;
- revoke approval;
- purge sensitive content.

## Retention

Minimum future retention classes:

- `session_only`;
- `temporary_ttl`;
- `durable_until_corrected`;
- `durable_until_deleted`;
- `source_backed_cache`;
- `historical_audit_retained`;
- `restricted_short_retention`.

Second Brain Phase 2 fixture-only validation should use only ordinary synthetic
durable test records.

## Sensitivity Boundary

Sensitivity classes:

- ordinary;
- personal;
- sensitive;
- restricted / never-store.

Never-store examples:

- credentials;
- authentication secrets;
- recovery codes;
- private keys;
- raw biometric templates.

Initial Phase 2 implementation must not persist real:

- health data;
- financial data;
- relationship data;
- private communications;
- precise location;
- intimate or private activity;
- biometric data.

Sensitive Memory remains a future gate.

## Multi-User Scope

Bounded user scope is required from the first implementation:

- `system`;
- `primary_user`;
- `household`;
- `guest_session`;
- `unknown`.

Rules:

- no cross-user recall;
- guest activity does not become owner memory;
- unknown identity cannot access personal durable memory;
- shared knowledge requires explicit scope.

Full identity and authentication integration is not required for fixture-only
validation, but user-scope isolation must be testable.

## Source Of Truth Interaction

GitHub-backed and Notion-backed knowledge must not become detached copies that
silently outrank their current sources.

Future source-backed durable records should contain:

- source reference;
- bounded snapshot summary;
- PR, commit or page reference where relevant;
- freshness;
- supersession links.

When live authoritative source verification exists:

```text
current GitHub/Notion truth
>
stale cached memory snapshot
```

Explicit user-approved local memory may be authoritative for that scoped user
fact or preference.

## Storage Adapter Boundary

Recommended narrow architecture:

```text
Second Brain diagnostic/retrieval
-> KnowledgeRepository
-> InMemoryKnowledgeRepository
-> future SQLiteKnowledgeRepository
-> immutable KnowledgeItem
-> existing deterministic retrieval
-> RetrievalResult
```

Do not create a generic storage or repository framework.

## Phase 1 Compatibility

Persistence must preserve the current Phase 1 flow:

```text
storage
-> immutable KnowledgeItem
-> current deterministic retriever
-> RetrievalResult
-> text/JSON diagnostic
```

Do not rewrite Phase 1 ranking semantics merely because persistence exists.

## Atomicity

Future SQLite implementation must guarantee atomic:

- insert;
- correction plus supersession;
- logical delete;
- purge;
- migration or version update.

A correction must never leave:

- new record committed;
- old record still current.

## Concurrency

Initial implementation may use:

- single-process serialized writes;
- SQLite normal readers;
- no distributed locking;
- no background worker.

Distributed storage is not approved.

## Schema And Versioning

Future implementation requires:

- explicit schema version;
- supported current version;
- safe handling of unsupported future or old versions;
- no silent downgrade;
- deterministic initialization;
- migration hooks before real user data.

This ADR PR does not implement migrations.

## Failure Isolation

If storage is missing, corrupt, incompatible, write denied, disk full or
malformed:

- Runtime continues;
- `DeviceState` continues;
- explicit commands continue;
- Second Brain degrades to unavailable, read-only or unknown;
- writes fail explicitly;
- no memory is fabricated;
- silent success is not reported.

## Encryption And Security

SQLite alone is not a security boundary.

For fixture-only Phase 2:

- synthetic non-sensitive data only;
- ignored/local DB path;
- OS account and file permissions are acceptable for validation.

Before real personal memory:

- at-rest encryption decision is required;
- key ownership is required;
- backup implications are required;
- Sensitive Memory gate is required.

Encryption is not a blocker for synthetic fixture-only validation.

## Observability And Logging

Allowed diagnostics:

- storage health;
- schema version;
- item counts by safe category or scope;
- last successful write time;
- migration state;
- safe error codes.

Forbidden logs:

- raw memory content;
- sensitive summaries;
- raw SQL containing personal data;
- full DB dumps;
- credentials;
- connector payloads.

## Backup And Export

Future-only capabilities:

- export;
- import;
- backup;
- encrypted backup;
- user inspection.

They are not required for the first fixture-only implementation.

## Explicit Non-Decisions

This ADR does not approve:

- real personal memory storage;
- sensitive memory storage;
- automatic memory extraction;
- automatic profiling;
- connectors;
- GitHub indexing;
- Notion indexing;
- Obsidian integration;
- Drive indexing;
- embeddings;
- vector DB;
- semantic search;
- RAG;
- provider-backed retrieval;
- AI durable writes;
- API or Dashboard exposure;
- Runtime execution;
- cross-device or cloud sync.

## Phase 2 Implementation Authorization Boundary

After this ADR is reviewed and merged, the smallest implementation that may be
authorized is:

```text
Second Brain Phase 2 - SQLite Fixture Persistence
```

Scope:

- local SQLite repository;
- synthetic ordinary/non-sensitive fixtures only;
- insert;
- list and get;
- deterministic reload;
- explicit correction plus supersession;
- logical delete;
- hard purge;
- schema version check;
- user-scope isolation;
- local diagnostic only;
- Phase 1 retrieval parity.

Still prohibited:

- real personal or sensitive memory;
- connectors;
- RAG;
- embeddings;
- AI writes;
- API or Dashboard exposure;
- Runtime authority.

## Required Future Gates

Do not create these now:

- Sensitive Memory / Retention gate;
- Source Connector / Indexing gate;
- Semantic Retrieval / RAG gate;
- Multi-user / identity gate if bounded `user_scope` becomes insufficient.

Avoid ADR explosion.

## Future Implementation Direction

The next implementation gate, if explicitly opened after this ADR is reviewed
and merged, should be `Second Brain Phase 2 - SQLite Fixture Persistence`.

It should remain local, fixture-only, deterministic, non-executing and
independent from Runtime, Planner, Drivers, `DeviceState`, API, Dashboard, AI and
connectors.
