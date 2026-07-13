# Troubleshooting Device Integration

Status: Current / Experimental HTTP Local Troubleshooting

## `Device command failed`

This is a safe adapter-facing failure. It may come from invalid configuration, unavailable device, timeout, invalid response, unsupported operation, or missing capability.

Check:

- The device is registered.
- The capability exists on the device.
- The validation runtime is running, not the default runtime.
- The ESP32 is powered and connected to the same local network.

## ESP32 Does Not Respond

Check basic reachability:

```powershell
ping <IP>
```

If ping fails, check power, Wi-Fi, local network isolation, firewall, and hotspot settings.

## IP Changed

The validation runtime uses an explicit base URL. Restart it with the current ESP32 IP:

```powershell
python tools/run_http_led_validation.py --base-url http://<IP>
```

## Test Directly With PowerShell

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://<IP>/device/apply" `
  -ContentType "application/json" `
  -Body '{"capability":"power.switch","parameters":{"state":"true"}}'
```

## Timeout

Possible causes:

- ESP32 offline.
- Wrong IP.
- Host and ESP32 are on different networks.
- Hotspot client isolation.
- Firmware server not started.

JarvisOS should return a safe error without exposing URL, payload, headers, exceptions, or stack traces.

## Invalid JSON Or Content Type

The HTTP protocol requires JSON responses with:

- Root object.
- `success` boolean.
- `observations` object.
- `error` string or null.
- JSON content type.

## Capability Not Supported

The ESP32 HTTP LED example supports:

- `power.switch`
- `status.read`

Unsupported capabilities should return:

```json
{
  "success": false,
  "observations": {},
  "error": "operation_not_supported"
}
```

## Device Not Registered

The default runtime starts with no devices.

For the ESP32 LED validation, use:

```powershell
python tools/run_http_led_validation.py --base-url http://<IP>
```

## Binding Not Configured

The default runtime does not configure HTTP bindings. Use the validation runtime or an explicit test runtime.

For declarative configuration, use:

```powershell
python -m jarvis_core --config profiles/http-lab.local.json
```

See [Runtime Configuration](../getting-started/CONFIGURATION.md).

For the ESP32 profile-based validation flow, use:

```powershell
python -m jarvis_core --config profiles/http-lab.local.json
```

See [HTTP Profile Validation](../getting-started/HTTP_PROFILE_VALIDATION.md).

## State Store Problems

If a configured runtime reports:

```text
State store is corrupt.
```

the JSON snapshot is invalid or unsupported. JarvisOS stops startup rather than silently operating with state the user expects to be restored.

If the state file is missing, startup should continue with an empty store. State files are experimental snapshots and should not be committed.

See [Device State Persistence](../getting-started/STATE_PERSISTENCE.md).

## `device state` Only Shows Status

State changes only appear after successful `device read` or `device apply` operations return accepted observations.

With a State Store, restored state is marked `stale` until a fresh read or apply produces new observations. `stale` means last known semantic state, not current hardware availability.

## ESP-IDF Monitor

Use the ESP-IDF monitor from the firmware project directory:

```powershell
idf.py monitor
```

Use the monitor to distinguish firmware errors from JarvisOS driver errors.

