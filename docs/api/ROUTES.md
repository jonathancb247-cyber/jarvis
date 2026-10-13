# Runtime API Routes

Status: Current / Experimental

Base URL:

```text
http://127.0.0.1:8765
```

The server binds to localhost only.

## Health

```http
GET /api/v1/health
```

Response:

```json
{
  "status": "ok",
  "prototype": "AVP-001",
  "device_count": 1,
  "persistence_enabled": true,
  "profile_name": "http-lab"
}
```

## Devices

```http
GET /api/v1/devices
```

Response:

```json
{
  "devices": [
    {
      "device_id": "lamp_1",
      "name": "ESP32 LED",
      "type": "light",
      "status": "stale",
      "is_current": false,
      "capability_count": 2
    }
  ]
}
```

## Device Detail

```http
GET /api/v1/devices/lamp_1
```

Returns safe device identity, formal capabilities, semantic state properties, and `updated_at`.

## Capabilities

```http
GET /api/v1/devices/lamp_1/capabilities
```

Each capability exposes only:

- `name`;
- `kind`;
- safe parameter descriptors with `type` and `required`.

## State

```http
GET /api/v1/devices/lamp_1/state
```

Response:

```json
{
  "device_id": "lamp_1",
  "status": "stale",
  "is_current": false,
  "semantic_properties": {
    "power": false
  },
  "updated_at": "2026-07-13T12:00:00+00:00"
}
```

State mapping:

```text
known   -> is_current = true
unknown -> is_current = false
stale   -> is_current = false
```

`stale` means last-known semantic state. It does not prove current device availability.

## Commands

```http
POST /api/v1/commands
Content-Type: application/json
```

Request:

```json
{
  "input": "device apply lamp_1 power.switch state=true"
}
```

Success response:

```json
{
  "success": true,
  "message": "Device action completed.",
  "error": null
}
```

Failure response:

```json
{
  "success": false,
  "message": "Device command failed.",
  "error": "device_execution_failed"
}
```

The exact `error` value is the safe Runtime or CapabilityResult error code. The API accepts only one canonical deterministic JarvisOS command string. It does not accept natural language, structured `Command` objects, or `AIActionPlan`.

## Interactions (interaction-only mode)

The interaction endpoint is mounted **only** when the API is started in explicit
interaction-only mode:

```bash
python -m jarvis_core.api --config profiles/http-lab.local.json \
  --interaction-only \
  --interaction-provider-model gemma-2b
```

In this mode `POST /api/v1/commands` is disabled (returns `api_route_not_found`)
and the read-only projections above remain available. The bearer token is read
from the environment variable named by `--interaction-token-env`
(default `JARVIS_API_INTERACTION_TOKEN`); the process fails to start without it.

```http
POST /api/v1/interactions
Content-Type: application/json
Authorization: Bearer <token>
```

Request:

```json
{
  "message": "hola"
}
```

The message is preserved literally: it must be a printable, already-trimmed
string up to 4096 characters. Unknown fields, non-string values, control
characters, surrounding whitespace, and over-long messages are rejected.

Conversation response (pure greeting, no provider call):

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

Understanding response (delegated to the deterministic local understanding
boundary; canonical command text is never exposed):

```json
{
  "schema_version": 1,
  "type": "understanding",
  "response_text": "",
  "commands_executed": false,
  "decision": {
    "status": "executable_candidate",
    "resolver_kind": "execute",
    "confirmation_required": true,
    "commands_executed": false
  },
  "success": true,
  "error": null
}
```

The endpoint is strictly non-executing. It does not call Runtime, Drivers, the
Planner, or the ExecutionGate, and `commands_executed` is always false. An
`executable_candidate` is only a validated candidate that would still require the
normal confirmation and policy path before any execution. It is never
authorization.

Status mapping preserves the provider and decision outcome:

```text
conversation / executable_candidate / needs_clarification / refused -> 200
local AI provider unavailable                                        -> 503
local AI provider timeout                                            -> 504
invalid provider response                                            -> 502
```

## Errors

API errors use safe codes:

- `api_request_invalid`;
- `api_route_not_found`;
- `api_method_not_allowed`;
- `api_payload_too_large`;
- `api_command_invalid`;
- `api_runtime_unavailable`;
- `api_response_serialization_failed`;
- `api_unauthorized`;
- `api_interaction_busy`;
- `api_interaction_provider_unavailable`;
- `api_interaction_provider_timeout`;
- `api_interaction_provider_invalid`.

Runtime execution failures are mapped from safe Runtime and CapabilityResult errors.
