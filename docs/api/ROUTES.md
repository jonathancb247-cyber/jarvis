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

## Errors

API errors use safe codes:

- `api_request_invalid`;
- `api_route_not_found`;
- `api_method_not_allowed`;
- `api_payload_too_large`;
- `api_command_invalid`;
- `api_runtime_unavailable`;
- `api_response_serialization_failed`.

Runtime execution failures are mapped from safe Runtime and CapabilityResult errors.
