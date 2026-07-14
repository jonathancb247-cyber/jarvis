# HTTP Profile Validation

Status: Current / Manual Hardware Validation

This guide validates the complete HTTP profile flow with a real ESP32 and the persisted `DeviceState` store.

Validated path:

```text
profile JSON
-> RuntimeConfigurationLoader
-> RuntimeProfile
-> bootstrap
-> DeviceRegistry
-> HttpDeviceBindingStore
-> JsonDeviceStateStore restore
-> Runtime
-> HttpDeviceDriver
-> ESP32
-> DeviceState update
-> atomic save
-> shutdown
-> restart
-> stale restore
```

Hardware validation is manual. CI uses a fake HTTP transport and must not require an ESP32.

## Create A Local Profile

Copy the versioned example profile:

```powershell
Copy-Item `
  profiles/http-lab.example.json `
  profiles/http-lab.local.json
```

Edit `profiles/http-lab.local.json` and replace:

```json
"base_url": "http://192.168.1.50"
```

with:

```json
"base_url": "http://<IP_DEL_ESP32>"
```

Do not commit the local profile. `profiles/*.local.json` is ignored by Git.

The profile must define:

- Device `lamp_1`
- `power.switch`
- `status.read`
- one HTTP binding for `lamp_1`
- `runtime_options.state_store_path` set to `../state/http-lab.state.json`

Do not add secrets, credentials, tokens, TLS, retries, or extra runtime options.

## Start JarvisOS With The Profile

```powershell
python -m jarvis_core --config profiles/http-lab.local.json
```

The default runtime is not used. The Phase 8.4 validation script is not required for this flow.

## Commands

Run these commands inside JarvisOS:

```text
device list
device info lamp_1
device capabilities lamp_1
device state lamp_1
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
device state lamp_1
device apply lamp_1 power.switch state=false
device read lamp_1 status.read
device state lamp_1
```

Expected behavior:

- `lamp_1` exists from config.
- Capabilities are formal.
- Initial state is `unknown` when no snapshot exists.
- `state=true` turns the LED on.
- `state=false` turns the LED off.
- `device read` obtains the ESP32-reported state.
- State becomes `known` after accepted observations.
- A state snapshot is saved under `state/http-lab.state.json`.

## Restart Validation

1. Start with no `state/http-lab.state.json`.
2. Run `python -m jarvis_core --config profiles/http-lab.local.json`.
3. Turn the LED on.
4. Run `device read lamp_1 status.read`.
5. Confirm `device state lamp_1` reports `known`.
6. Exit normally with `exit`.
7. Confirm `state/http-lab.state.json` exists.
8. Restart with the same profile.
9. Before a new hardware read, confirm:
   - `lamp_1` exists.
   - state is `stale`.
   - previous semantic properties are preserved.
10. Run:

```text
device read lamp_1 status.read
```

11. Confirm state becomes `known` again.
12. Turn the LED off.
13. Exit.
14. Restart again and confirm stale state reflects the latest saved semantic properties.

Restored state is last-known semantic state. It is not proof that the ESP32 is currently reachable.

## Failure Validation

With the runtime running:

1. Disconnect the ESP32 or hotspot.
2. Run:

```text
device read lamp_1 status.read
```

Expected behavior:

- JarvisOS returns a safe failure.
- Runtime remains alive.
- Output does not expose URL, IP, stack trace, raw payload, headers, or exception text.
- Previous semantic state is not overwritten with technical error data.
- State does not become falsely `known`.

Reconnect the ESP32 and run a successful `device read` to confirm recovery.

No retries are implemented.

## State File

The configured state path is:

```text
state/http-lab.state.json
```

This file is ignored by Git. Delete it when you want to start from a clean state:

```powershell
Remove-Item state/http-lab.state.json
```

## Manual Validation Report Template

Copy this template into a local note. Do not commit personal identifiers or secrets.

```text
Date:
Host OS:
Python version:
ESP32 model:
ESP-IDF version:
Profile path:
State file path:

Apply on result:
Read result:
Apply off result:
Restart stale result:
Post-restart read result:
Disconnected device result:

Privacy verification:
- No URL/IP exposed:
- No raw payload exposed:
- No headers exposed:
- No exceptions or stack traces exposed:
- No secrets committed:
```

## Security Limits

This remains experimental local-network validation.

Not implemented:

- authentication
- TLS
- secrets
- retries
- async/background I/O
- DriverRegistry
- hardware discovery
- automatic onboarding
