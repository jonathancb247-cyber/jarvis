# Windows PC Integration

Status: Current / Host Supported

## Overview

Windows PCs can run JarvisOS as a host and development environment.

## Current Support

- PowerShell.
- Python source checkout.
- Unit tests.
- Default offline-safe runtime.
- Optional HTTP LED validation runtime.

## Possible Architectures

```text
Windows PC
-> JarvisOS Host
-> Local network ESP32
```

## Requirements

- Python available as `python`.
- Git.
- PowerShell.

WSL is not required for the current Python runtime.

## Recommended Transport

HTTP local for explicit hardware validation.

## Setup

```powershell
git clone <repository-url>
cd jarvis
python -m unittest
python -m jarvis_core
```

## JarvisOS Configuration

Use the default runtime for offline-safe tests. Use the validation tool for ESP32 hardware:

```powershell
python tools/run_http_led_validation.py --base-url http://<IP_DEL_ESP32>
```

Or start from an explicit JSON runtime profile:

```powershell
python -m jarvis_core --config profiles/http-lab.local.json
```

See [Runtime Configuration](../getting-started/CONFIGURATION.md), [Device State Persistence](../getting-started/STATE_PERSISTENCE.md), and [HTTP Profile Validation](../getting-started/HTTP_PROFILE_VALIDATION.md).

## Example Commands

```text
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
device state lamp_1
```

## Security

Windows firewall or hotspot isolation can block device communication. Keep ESP32 validation on a trusted local network.

## Limitations

- No installer.
- State persistence is experimental and limited to semantic `DeviceState`.
- No automatic hardware discovery.

## Troubleshooting

Use:

```powershell
ping <IP>
```

Then test HTTP directly with `Invoke-RestMethod`.

## Future Work

- Installer.
- Service-managed profile selection.
- Better local diagnostics.

