# Device Protocol

Status: Current / Experimental - HTTP Local Protocol

JarvisOS currently validates real device communication through a fixed local HTTP protocol.

## Principles

- The device does not receive `Command`.
- The device receives technical operations from the driver.
- The node returns observations.
- The driver produces `DriverResult`.
- `DeviceStateCoordinator` decides what enters official `DeviceState`.
- The protocol does not define trust, authorization, onboarding, discovery, or persistence.
- Capabilities are semantic and must not contain transport details.

## Apply

```http
POST /device/apply
Content-Type: application/json
```

Request:

```json
{
  "capability": "power.switch",
  "parameters": {
    "state": "true"
  }
}
```

Success:

```json
{
  "success": true,
  "observations": {
    "power": true
  },
  "error": null
}
```

## Read

```http
POST /device/read
Content-Type: application/json
```

Request:

```json
{
  "capability": "status.read"
}
```

Success:

```json
{
  "success": true,
  "observations": {
    "power": true
  },
  "error": null
}
```

## Error Response

```json
{
  "success": false,
  "observations": {},
  "error": "operation_not_supported"
}
```

## Response Contract

- The response root must be a JSON object.
- `success` must be a boolean.
- `observations` must be a JSON object.
- `error` must be a string or `null`.
- Payloads must be size-limited.
- Firmware must not return stack traces.
- Firmware must not return credentials.
- Binary payloads are not part of this protocol.
- Python serialization is not part of this protocol.
- Executable content is not part of this protocol.

## Firmware-Level Errors

The ESP32 HTTP LED example uses:

- `operation_not_supported`
- `invalid_request`
- `invalid_json`
- `invalid_parameters`

These are firmware response values. JarvisOS may normalize transport and protocol failures into internal `DriverResult.error` values such as `invalid_response`, `request_timeout`, or `connection_failed`.

## Compatibility

This protocol is compatible with the current `HttpDeviceDriver`.

The protocol is experimental. It is intended for local-network validation and is not production secure.

