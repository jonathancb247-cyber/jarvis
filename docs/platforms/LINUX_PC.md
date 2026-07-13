# Linux PC Integration

Status: Current / Host Supported

## Overview

Linux PCs can run JarvisOS as a host.

## Current Support

- Python source checkout.
- Unit tests.
- Default offline-safe runtime.
- Optional HTTP validation runtime when configured explicitly.

## Possible Architectures

```text
Linux PC
-> JarvisOS Host
-> Local network device
```

## Requirements

- Python.
- Git.
- Shell.

## Recommended Transport

For hardware validation, HTTP local is currently available through explicit runtime wiring.

## Setup

```bash
git clone <repository-url>
cd jarvis
python -m unittest
python -m jarvis_core
```

## JarvisOS Configuration

The default runtime does not open network connections or create demo devices.

## Example Commands

```text
device list
device discover
```

For ESP32 validation:

```bash
python tools/run_http_led_validation.py --base-url http://<IP_DEL_ESP32>
```

## Security

Use a controlled local network for HTTP devices.

## Limitations

- No installer.
- No package.
- No persistent configuration.

## Troubleshooting

Check Python version, repository path, firewall, and local network reachability.

## Future Work

- Installer or package.
- Service mode.
- Persistent configuration.

