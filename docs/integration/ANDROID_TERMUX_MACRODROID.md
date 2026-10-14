# Android / Termux + MacroDroid Integration

Status: Experimental (on-device guide, not yet physically validated)

This guide describes how to run the existing JarvisOS Runtime API in
interaction-only mode **inside Termux on the same Android phone** that hosts the
JarvisOS Companion app, and how to drive it from a MacroDroid automation.

It is a deployment/runbook guide only. It does not change Runtime, the Planner,
the ExecutionGate, drivers, transports, MQTT, or the Companion app, and it must
not be used to expose any listener beyond loopback.

## What this integration is

```text
MacroDroid (HTTP request)
-> http://127.0.0.1:8765/api/v1/interactions   (JarvisOS Core, Termux)
-> LocalInteractionService (non-executing)
   -> pure greeting: answered locally, no provider call
   -> other message: local understanding provider
-> http://127.0.0.1:8767/generate              (Companion, same device)
-> mounted non-executing response (commands_executed = false)
```

Because Termux and the Companion app run on the same device, they share the
Android loopback interface. Termux reaches the Companion on `127.0.0.1:8767`
directly, with no `adb forward` and no LAN traffic.

## What this integration is not

- It does not execute commands. The interaction endpoint never calls Runtime,
  Drivers, the Planner or the ExecutionGate, and every response reports
  `commands_executed = false`.
- It does not expose the API to a LAN or the internet. The server binds to
  loopback only.
- It does not modify the Companion app, MacroDroid, Runtime, the ExecutionGate
  or MQTT.
- It does not add retries, background polling, retry or fallback providers, or
  persistent AI memory.

See [Runtime API Routes](../api/ROUTES.md) and
[Runtime API Security](../api/SECURITY.md) for the exact, authoritative contract.

## Dependencies

The interaction-only path is **Python standard library only**:

- running the interaction endpoint needs no third-party Python package;
- the MQTT client (`paho-mqtt`) and the Windows TLS helper (`truststore`) listed
  in `requirements.txt` are **not** required for this path;
- `python`, `git` and `curl` are the only Termux packages this guide installs.

The example profile `profiles/android-termux.example.json` has no device
bindings and no `state_store_path`, so it starts an offline-safe, in-memory
profile with persistence disabled and no state writes.

## Prerequisites on the phone

- Termux installed.
- The JarvisOS Companion app installed (optional for the greeting test; required
  later for non-greeting interpretation).
- MacroDroid installed (optional; any local HTTP client works for the greeting
  test).

## Step-by-step

Run every command **inside Termux**, from the repository root.

### 1. Get the repository into Termux

Clone the repository (or copy it) into the Termux home directory. Git is
installed by the bootstrap step below if it is missing.

### 2. Bootstrap Termux (idempotent)

```bash
bash tools/termux/bootstrap_termux.sh
```

This installs `python`, `git` and `curl`, and creates a private data directory
at `$HOME/.jarvisos`. It is safe to run repeatedly.

### 3. Generate the local token (never stored in Git)

```bash
python tools/termux/make_interaction_token.py
```

The token is written to `$HOME/.jarvisos/interaction.token` (mode `0600`) and is
**never printed**. The file lives outside the repository and is not tracked by
Git. To replace it deliberately, add `--force`.

### 4. Create the local profile

```bash
cp profiles/android-termux.example.json profiles/android-termux.local.json
```

`profiles/*.local.json` is git-ignored, so this copy is never committed. The
example profile is neutral (no addresses, no secrets, no state path); edit the
local copy if a different device set is needed.

### 5. Start the interaction endpoint

```bash
JARVISOS_MODEL=<local-understanding-model-id> \
  bash tools/termux/run_core_interaction.sh
```

This runs:

```text
python -m jarvis_core.api --config profiles/android-termux.local.json \
  --interaction-only \
  --interaction-token-env JARVIS_API_INTERACTION_TOKEN \
  --interaction-provider-model <local-understanding-model-id> \
  --interaction-provider-host 127.0.0.1 \
  --interaction-provider-port 8767
```

The process fails closed if the token file, the profile or the model id is
missing. The model id is an opaque identifier passed to the local provider; the
pure greeting test does not invoke it, but the API still requires one to start.

Optional: run `termux-wake-lock` in a second Termux session to reduce the chance
that Android suspends Termux while the endpoint is running.

### 6. Smoke test (read-only)

In a second Termux session:

```bash
bash tools/termux/smoke_interaction.sh
```

Expected results:

```text
GET  /api/v1/health                         -> 200
POST /api/v1/interactions (no token)        -> 401 (api_unauthorized)
POST /api/v1/interactions (wrong token)     -> 401 (api_unauthorized)
POST /api/v1/interactions "hola" + token    -> 200 (commands_executed=false)
POST /api/v1/commands (interaction-only)    -> 404 (api_route_not_found)
```

### 7. Configure MacroDroid

Create an HTTP Request action:

- Method: `POST`
- URL: `http://127.0.0.1:8765/api/v1/interactions`
- Header: `Content-Type: application/json`
- Header: `Authorization: Bearer <token from $HOME/.jarvisos/interaction.token>`
- Body: `{"message":"hola"}`

The free version of MacroDroid supports HTTP Request actions. If the request is
blocked, confirm that MacroDroid allows cleartext loopback HTTP (see
Limitations).

### 8. Interpretation test (optional, requires the Companion)

Only a pure greeting (`hola`, `hola jarvis`, `hey jarvis`, `buenas`,
`buenos dias`, `buenas tardes`, `buenas noches`) is answered locally. Any other
message is delegated to the local understanding provider at
`127.0.0.1:8767`, which requires the Companion app to be running with a model
loaded. Without it, a non-greeting request returns HTTP 503 or 504 rather than a
successful conversation. The canonical command text is never exposed in the
response.

## Request and response contract

```http
POST /api/v1/interactions
Content-Type: application/json
Authorization: Bearer <token>
```

```json
{ "message": "hola" }
```

Pure greeting response:

```json
{
  "schema_version": 1,
  "type": "conversation",
  "response_text": "Hola. ¿En qué puedo ayudarte?",
  "commands_executed": false,
  "decision": null,
  "success": true,
  "error": null
}
```

The message is preserved literally: it must be a printable, already-trimmed
string up to 4096 characters. Unknown fields, non-string values, control
characters, surrounding whitespace and over-long messages are rejected.

Status mapping:

```text
conversation / executable_candidate / needs_clarification / refused -> 200
missing, malformed or wrong bearer token                            -> 401
local AI provider unavailable                                       -> 503
local AI provider timeout                                           -> 504
invalid provider response                                           -> 502
command route in interaction-only mode                              -> 404
```

## Security notes

- The token file lives at `$HOME/.jarvisos/interaction.token`, outside the
  repository, and is never printed or committed.
- The API binds to `127.0.0.1` only. Do not expose it to a LAN or the internet.
- In interaction-only mode `POST /api/v1/commands` is disabled, so this path
  cannot trigger device execution.
- The guide never installs, updates or removes Android applications, never uses
  `adb` against private app storage, and never writes to the device profile.

## Limitations

- Confirming the Termux Python environment requires running commands **inside
  Termux**; `adb` cannot read Termux private storage without root.
- MacroDroid (a Java/OkHttp app) may be subject to Android cleartext-traffic
  policy for `http://127.0.0.1`. Termux raw sockets are not affected.
- The Companion must be running with a model loaded before non-greeting
  messages can be interpreted.
- Battery optimisation may suspend Termux; use `termux-wake-lock` if needed.
- This guide is not physically validated yet. It is prepared for an independent
  review before any on-device deployment.

## Automated checks in this repository

The repository ships unit tests that validate these assets without a device:

```bash
python -m unittest tests.test_android_termux_integration
```

They confirm that the example profile is valid, offline-safe and free of
addresses/secrets, that it builds a runtime without network access, and that the
token tool writes a valid token without ever printing it.
