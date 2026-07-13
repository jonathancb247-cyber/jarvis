# Raspberry Pi Integration

Status: Partial / Future

## Overview

Raspberry Pi can run JarvisOS as a host. It may also act as an HTTP node or future GPIO controller.

## Current Support

Current:

- Host role, if Python and Git are available.

Future:

- Local GPIO driver.
- Raspberry Pi as a managed device node.
- Persistent service setup.

## Possible Architectures

```text
Raspberry Pi
-> JarvisOS Host
```

```text
JarvisOS Host
-> HTTP local
-> Raspberry Pi node
-> GPIO
```

## Requirements

For host usage:

- Python.
- Git.
- Terminal access.

For future GPIO usage:

- GPIO driver design.
- Permission model.
- Hardware safety model.

## Recommended Transport

Host usage is current. HTTP node usage is possible conceptually. GPIO local is future.

## Setup

Use the general [Installation](../getting-started/INSTALLATION.md) guide for host setup.

## JarvisOS Configuration

The default runtime remains offline-safe and does not configure hardware automatically.

## Example Commands

Host commands match the normal JarvisOS CLI.

## Security

Do not confuse running JarvisOS on Raspberry Pi with granting access to physical GPIO. GPIO control requires explicit future design.

## Limitations

- No official GPIO driver.
- No hardware GPIO validation.
- No service installer.

## Troubleshooting

Check Python, Git, file permissions, and terminal environment.

## Future Work

- GPIO boundary.
- Service setup.
- Hardware safety guidelines.

