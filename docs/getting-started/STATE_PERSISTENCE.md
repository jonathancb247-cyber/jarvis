# Device State Persistence

Status: Current / Experimental State Store

JarvisOS can persist the last approved semantic `DeviceState` for configured devices when an explicit runtime profile enables a state store.

Configuration and state are separate:

```text
Configuration
-> defines Device, DeviceCapability, and HttpDeviceBinding

State Store
-> stores the last safe semantic DeviceState snapshot
```

The default runtime does not use a State Store, does not read or write state files, and remains offline-safe.

## Enabling The State Store

Add `state_store_path` to a local profile:

```json
{
  "runtime_options": {
    "state_store_path": "../state/http-lab.state.json"
  }
}
```

Only this runtime option is supported. Unknown runtime options are rejected.

Relative paths resolve relative to the configuration file location. The example above is intended for a profile under `profiles/`, with snapshots written under `state/`.

Do not commit state snapshots. The repository ignores:

```text
state/
*.state.json
```

## Snapshot Schema

State snapshots use schema version `1`:

```json
{
  "schema_version": 1,
  "states": {
    "lamp_1": {
      "status": "stale",
      "properties": {
        "power": true
      },
      "updated_at": "2026-07-13T12:00:00+00:00"
    }
  }
}
```

The store persists only:

- `device_id`
- `status`
- semantic `properties`
- `updated_at`

It does not persist configuration, bindings, URLs, credentials, candidates, trust, raw driver results, raw HTTP payloads, request history, stack traces, or diagnostics.

## Restore Policy

At startup, JarvisOS restores state only for devices declared by the active profile.

Rules:

- Missing state file starts as an empty store.
- Orphan states do not create devices.
- A saved `unknown` status restores as `unknown`.
- Any other saved status restores as `stale`.
- Restored state is the last known semantic state, not proof that hardware is currently online.

## Save Policy

JarvisOS saves after an official `DeviceState` update and also attempts a final save on controlled CLI shutdown (`exit`, `quit`, or EOF).

Save failures do not rewrite a successful physical operation into a failed device command. The in-memory state remains authoritative for the running process.

## Corrupt State

A corrupt or unsupported state snapshot fails startup with a safe message, such as:

```text
State store is corrupt.
```

Startup errors do not expose full paths, snapshot contents, properties, exceptions, or stack traces.

## Not Implemented

This phase does not implement:

- SQLite
- migrations
- history
- append-only logs
- event sourcing
- cloud sync
- multi-process locking
- background saving
- secrets
- credentials
- encryption
- persistent trust
- candidate persistence
- retry policy
