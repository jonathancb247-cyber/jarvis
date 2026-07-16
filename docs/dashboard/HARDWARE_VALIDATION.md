# Dashboard Hardware Validation

Status: Current / Experimental

Phase 11.4 validates the existing Dashboard against the profile-based HTTP ESP32 integration. It is a validation phase, not a feature phase. It does not add AI, authentication, LAN access, retries, WebSocket, SSE, async Runtime behavior, or new architecture.

Validated path:

```text
Dashboard
-> Runtime API
-> Runtime.handle_adapter_input(...)
-> Planner
-> Runtime
-> HttpDeviceDriver
-> ESP32
-> DeviceState
-> JsonDeviceStateStore
-> Dashboard projection
```

Related guides:

- [Dashboard Usage](USAGE.md)
- [Dashboard Security](SECURITY.md)
- [Runtime API](../api/README.md)
- [Runtime API Security](../api/SECURITY.md)
- [HTTP Profile Validation](../getting-started/HTTP_PROFILE_VALIDATION.md)
- [Device State Persistence](../getting-started/STATE_PERSISTENCE.md)
- [Runtime Configuration](../getting-started/CONFIGURATION.md)

## Preconditions

- Work from the current `main` branch with a clean tracked working tree.
- Create `profiles/http-lab.local.json` from `profiles/http-lab.example.json`.
- Keep `profiles/http-lab.local.json` gitignored.
- Keep `state/http-lab.state.json` gitignored.
- Configure the local profile for the current ESP32 address without committing it.
- Confirm the profile contains `lamp_1`.
- Confirm `lamp_1` declares `power.switch` and `status.read`.
- Confirm the ESP32 firmware is running and the host is on the same network.
- Confirm no AI provider, API key, Groq, Ollama, or AI chat is required.

Do not commit personal IP addresses, SSIDs, credentials, or state snapshots.

## Startup

Start the Dashboard explicitly:

```powershell
python -m jarvis_core.dashboard `
  --config profiles/http-lab.local.json `
  --port 8765
```

Expected local URL:

```text
http://127.0.0.1:8765/
```

The Dashboard must bind only to localhost. Stop it with `Ctrl+C` so the Runtime shutdown hook can save the state snapshot.

Do not run the API-only entry point when validating Dashboard static assets. API-only mode is validated separately with:

```powershell
python -m jarvis_core.api --config profiles/http-lab.local.json
```

## Initial Unknown State

Before the first run, remove or back up the ignored state snapshot:

```powershell
Remove-Item state\http-lab.state.json -ErrorAction SilentlyContinue
```

Expected result:

- Dashboard loads.
- Runtime health is visible.
- `lamp_1` appears.
- Device type is `light`.
- Formal capabilities appear.
- State is `unknown`.
- `unknown` is shown as not current.
- No online or availability claim is invented.
- No HTTP read or apply request occurs merely because the Dashboard starts.
- No fake devices, capabilities, history, metrics, charts, AI status, or state values appear.

Evidence:

- Safe route/status summaries.
- Dashboard screenshot without personal IPs.
- Device list/state projection showing `unknown` and not current.

## Real Read

Use the Dashboard `status.read` control.

Expected canonical command:

```text
device read lamp_1 status.read
```

Validate:

- Dashboard generates the canonical command.
- The command is submitted through `POST /api/v1/commands`.
- The API enters JarvisOS through `Runtime.handle_adapter_input(...)`.
- Planner parses the command.
- `HttpDeviceDriver` performs the real HTTP request.
- A safe result returns to the Dashboard.
- `DeviceState` becomes `known`.
- Returned semantic properties, such as `power`, appear when supplied by the device.
- No URL, IP, headers, raw payload, exception, stack trace, binding, or state path is displayed.

Software evidence is the safe Dashboard/API result and state transition. Physical evidence is the user's observation that the ESP32 remained reachable and reported the expected state.

## Real Mutations

Use the Dashboard controls for:

```text
device apply lamp_1 power.switch state=true
device apply lamp_1 power.switch state=false
```

Validate:

- Controls are generated only from formal capability descriptors.
- A user click is required.
- A visible confirmation is required before mutation commands.
- No background or automatic mutation occurs.
- Commands are submitted through Runtime API.
- State updates only from approved execution results.
- Dashboard refresh reflects the latest semantic state.
- Unsupported controls are not invented.

Software HTTP success is not visual proof. The user must manually confirm:

```text
PHYSICAL_LED_ON_CONFIRMATION_PENDING
PHYSICAL_LED_OFF_CONFIRMATION_PENDING
```

## Final Manual Validation Evidence

Phase 11.4 final hardware validation was completed manually against the real
ESP32 Dashboard workflow.

Confirmed software path:

```text
Dashboard
-> Runtime API
-> Runtime.handle_adapter_input(...)
-> Planner
-> Runtime
-> HttpDeviceDriver
-> ESP32
-> DeviceState
-> JsonDeviceStateStore
-> Dashboard projection
```

Confirmed manual evidence:

- Dashboard loaded at `http://127.0.0.1:8765/`.
- Runtime API status showed Connected.
- `lamp_1` appeared as type `light`.
- Formal capabilities appeared: `power.switch` and `status.read`.
- Real `status.read` succeeded.
- Device state became `known` and current.
- A real semantic `power` value was displayed when returned by the device.
- `power.switch state=true` succeeded through Dashboard/API/Runtime/HTTP Driver.
- LED on: confirmed manually.
- `power.switch state=false` succeeded through Dashboard/API/Runtime/HTTP Driver.
- LED off: confirmed manually.
- Clean shutdown saved the semantic state snapshot.
- Restart restored the prior semantic state as `stale` and not current.
- A new real read changed `stale` to `known` and not current to current.
- Disconnect: confirmed manually.
- While the ESP32 was disconnected, the Dashboard, Runtime API and Runtime
  remained alive.
- During the unreachable period the Dashboard may display `Loading`; this was
  observed as a temporary, recoverable state.
- Reconnect: confirmed manually.
- After reconnecting the ESP32, polling recovered automatically, status returned
  to Connected and no page reload was required.

Recorded state transitions:

```text
no snapshot -> unknown
real read -> known/current
clean restart -> stale/not current
real read -> known/current
ESP32 disconnected -> safe temporary failure/loading
ESP32 reconnected -> automatic recovery/Connected
```

Loading-state classification:

```text
UX observation - non-blocking
```

This observation is not a Phase 11.4 product defect because the Dashboard did
not crash, did not expose technical data, and recovered automatically after the
ESP32 reconnected. Do not add a new `Unavailable` state as part of Phase 11.4.

## Persistence And Restart

Validation sequence:

1. Start with no state file.
2. Confirm Dashboard shows `unknown`.
3. Perform a real read or mutation.
4. Confirm state becomes `known`.
5. Stop Dashboard cleanly.
6. Confirm the ignored state snapshot exists.
7. Inspect only approved semantic fields: `schema_version`, status, semantic properties, and `updated_at`.
8. Restart Dashboard.
9. Confirm `lamp_1` still appears.
10. Confirm restored state is `stale`.
11. Confirm semantic properties are preserved.
12. Confirm `stale` is shown as not current.
13. Perform a new real read.
14. Confirm state returns to `known`.
15. Stop Dashboard cleanly again.
16. Confirm the latest semantic state was saved.

Accepted rule:

```text
restored state does not imply current physical availability
```

## Controlled Failure And Recovery

Use a safe reversible physical failure if possible, such as disconnecting the ESP32 or turning off its network. Then issue:

```text
device read lamp_1 status.read
```

Expected result:

- Safe command failure.
- Dashboard remains usable.
- Runtime API remains alive.
- Runtime remains alive.
- Prior semantic state is preserved.
- State is not falsely changed to `known`.
- No retry loop or background retry occurs.
- No technical error is persisted.
- No URL, IP, header, payload, exception, or stack trace is exposed.

After reconnecting the ESP32, perform another real read and confirm recovery to `known`.

If Codex cannot physically disconnect and reconnect the device, report:

```text
PHYSICAL_DISCONNECT_RECONNECT_REQUIRED
```

## Honest Data Checks

Confirm the Dashboard displays only:

- Runtime API health.
- Safe device projections.
- Formal capabilities.
- Semantic `DeviceState`.

Confirm absence of:

- fake devices;
- fake capabilities;
- fake state properties;
- fake history;
- fake uptime;
- fake AI status;
- fake online/offline status;
- fake charts;
- unsupported controls;
- invented availability;
- invented persistence state.

## Boundary Checks

The Dashboard must not:

- import Runtime internals;
- construct `Command`;
- call Planner;
- call `DeviceCommandRouter`;
- call Drivers;
- mutate `DeviceRegistry`;
- read or write State Store directly;
- access `RuntimeContext`;
- access `EventBus`;
- access bindings;
- access profile secrets;
- use remote API endpoints;
- expose live Python objects.

Runtime API remains the only Dashboard backend boundary.

## Security And Privacy Checks

Validate:

- localhost bind only;
- no `0.0.0.0`;
- no LAN/public access;
- no wildcard CORS;
- no arbitrary static-file serving;
- no path traversal;
- no directory listing;
- no config/profile/state-file serving;
- no external CDN;
- no remote scripts;
- no `eval`;
- no untrusted `innerHTML`;
- no AI provider invocation;
- no API-key exposure;
- no raw Driver errors;
- no stack traces.

Authentication is not part of Phase 11.4.

## Visual Checklist

Desktop:

- sidebar alignment;
- overview cards;
- device list;
- selected-device state;
- capability controls;
- command console;
- API status;
- no overlapping or clipped text.

Mobile-width browser:

- stacked layout;
- usable navigation;
- tappable controls;
- accessible command input;
- visible text status meaning;
- no horizontal overflow;
- no controls disappear unexpectedly.

Do not claim real mobile-device validation unless performed on a real mobile device.

## Accessibility Checklist

- Semantic buttons.
- Labels.
- Keyboard navigation.
- Visible focus.
- Skip link.
- `aria-live` result areas.
- State meaning not conveyed only by color.
- Readable empty states.
- Mutation confirmation reachable by keyboard.
- No automatic focus trap.

Do not redesign the UI during validation unless a blocking defect is proven.

## Evidence Package

Minimum evidence:

- commands run;
- HTTP status summaries;
- Dashboard screenshots without personal IPs;
- semantic state snapshot summary;
- timestamps;
- transition table: `unknown`, `known`, `stale`, `known`;
- failure result;
- physical confirmation notes;
- test results;
- working-tree status.

Do not record raw HTTP traffic. Do not include personal IP addresses in committed evidence.

## Acceptance Criteria

Phase 11.4 can be accepted only when:

- Dashboard starts from the local profile.
- Real `lamp_1` appears.
- Real capabilities appear.
- Initial state is `unknown` without a snapshot.
- Read succeeds and produces `known`.
- Power on succeeds through Dashboard/API/Runtime/Driver.
- Power off succeeds through Dashboard/API/Runtime/Driver.
- Physical LED on/off changes are manually confirmed.
- Clean shutdown saves state.
- Restart restores `stale`.
- A new read restores `known`.
- A disconnected device fails safely.
- Runtime/API/Dashboard remain alive after failure.
- No technical data leaks.
- No fake data appears.
- Desktop and mobile-width checks pass.
- Automated tests pass.
- Default CLI remains unchanged.
- API-only entry point remains Dashboard-free.
- No AI provider is required.
- No architecture changes occur.

## Failure Classification

Classify blockers as:

- product defect;
- environment blocker;
- physical evidence pending;
- documentation inconsistency.

Completion is blocked by:

- hardware unavailable;
- invalid local profile;
- Dashboard cannot render the real device;
- command path bypasses Runtime API;
- unsafe error leakage;
- false availability claim;
- State Store inconsistency;
- mutation without user action;
- broken restart semantics;
- unusable visual UI;
- tracked local profile or state file;
- default Runtime regression.

Use:

```text
HARDWARE_DASHBOARD_VALIDATION_REQUIRED
```

when physical or visual evidence remains pending.
