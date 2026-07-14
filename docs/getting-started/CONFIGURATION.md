# Runtime Configuration

Status: Current / Experimental Configuration Loader

JarvisOS can build a runtime from an explicit JSON profile:

```bash
python -m jarvis_core --config path/to/profile.json
```

The default runtime remains offline-safe:

```bash
python -m jarvis_core
```

Without `--config`, JarvisOS does not load devices, HTTP bindings, profiles, network endpoints, hardware, or state persistence.

## Source Of Truth

GitHub is the source of truth for configuration schema examples and exact commands. Notion records architectural decisions and roadmap status.

## JSON Schema Version

Supported schema version:

```json
{
  "schema_version": 1
}
```

Only version `1` is accepted. Future schema versions are rejected until explicitly implemented.

## Minimal Profile Shape

```json
{
  "schema_version": 1,
  "profile": "http-lab",
  "devices": [],
  "http_bindings": [],
  "runtime_options": {}
}
```

Unknown fields are rejected.

## Devices

Devices are declarative configuration.

Each device must include:

- `id`
- `name`
- `type`
- `capabilities`
- `metadata`

`metadata` must be `{}` in this phase. Device state is not allowed in configuration.

## Capabilities

Capabilities must use formal `DeviceCapability` descriptors:

```json
{
  "name": "power.switch",
  "kind": "action",
  "parameters": {
    "state": {
      "type": "string",
      "required": true
    }
  },
  "constraints": {},
  "availability_policy": {}
}
```

Legacy string capabilities are not accepted in configuration profiles.

## HTTP Bindings

HTTP bindings are non-sensitive runtime configuration:

```json
{
  "device_id": "lamp_1",
  "base_url": "http://192.168.1.50",
  "timeout_seconds": 2.0,
  "read_path": "/device/read",
  "apply_path": "/device/apply"
}
```

The binding must reference a declared device. The underlying `HttpDeviceBinding` validation still applies.

Do not include:

- credentials
- tokens
- headers
- certificates
- arbitrary metadata
- secrets

## Runtime Options

Runtime options are strict. Phase 9.3 accepts either an empty object:

```json
"runtime_options": {}
```

or an explicit state store path:

```json
"runtime_options": {
  "state_store_path": "../state/http-lab.state.json"
}
```

`state_store_path` enables experimental DeviceState persistence. Relative paths resolve relative to the configuration file location. See [Device State Persistence](STATE_PERSISTENCE.md).

## Example Profile

Copy the example and edit it locally:

```powershell
Copy-Item profiles/http-lab.example.json profiles/http-lab.local.json
python -m jarvis_core --config profiles/http-lab.local.json
```

Local profiles are ignored by Git when named:

```text
profiles/*.local.json
```

The example file is versioned. Local files are user-specific.

The example profile includes a state store path. Running it may create an ignored state snapshot under `state/`.

For the full ESP32 profile-based validation workflow, see [HTTP Profile Validation](HTTP_PROFILE_VALIDATION.md).

## Startup Errors

Startup errors are safe and minimal:

- `Configuration file was not found.`
- `Configuration is invalid.`
- `Configuration schema version is not supported.`
- `Device configuration contains duplicates.`
- `Device capability configuration is invalid.`
- `HTTP device binding configuration is invalid.`
- `HTTP device binding references an unknown device.`

Startup errors do not print full JSON, full URLs, credentials, exception reprs, or stack traces.

## State Persistence

Configuration recreates Devices, capabilities, and HTTP bindings. The State Store preserves only safe semantic `DeviceState`.

On restart:

- missing state file starts empty;
- saved `unknown` restores as `unknown`;
- any other saved status restores as `stale`;
- hardware availability is not assumed.

## What Is Not Implemented

Phase 9.3 does not implement:

- `--profile`
- profile registry
- hot reload
- migrations
- TOML
- YAML
- secrets
- encryption
- retries
- async
- DriverRegistry

State history, secrets, trust, candidates, raw payloads, and technical driver results are not persisted.

