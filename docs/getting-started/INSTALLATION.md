# JarvisOS Installation

Status: Current / Development Setup

JarvisOS currently runs as a Python source checkout. There is no official installer, package, or release artifact yet.

## Requirements

- Python available as `python`.
- Git.
- A terminal:
  - Windows PowerShell on Windows.
  - A POSIX shell on Linux.

JarvisOS currently uses the Python standard library for its core runtime and test suite. Check the repository source and CI configuration before assuming additional dependencies.

## Clone Or Open The Repository

Windows PowerShell:

```powershell
git clone <repository-url>
cd jarvis
```

Linux shell:

```bash
git clone <repository-url>
cd jarvis
```

If you are already working inside a Codex workspace or an existing checkout, open the repository root before running commands.

## Run The Test Suite

Windows PowerShell:

```powershell
python -m unittest
```

Linux shell:

```bash
python -m unittest
```

All tests should pass before making changes or validating hardware.

## Start JarvisOS

```bash
python -m jarvis_core
```

The default runtime is offline-safe. It does not open network connections, does not create demo devices, and does not load hardware automatically.

To start from an explicit JSON profile, read [Runtime Configuration](CONFIGURATION.md). For experimental DeviceState snapshots, read [Device State Persistence](STATE_PERSISTENCE.md).

## Current Limitations

- No official installer.
- No official package.
- State persistence is experimental and limited to semantic `DeviceState`.
- No automatic hardware discovery.
- No production authentication or TLS for local HTTP devices.
- Hardware validation entry points are explicit tools, not the default runtime.

