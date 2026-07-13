# First Run

Status: Current / Implemented

Start JarvisOS from the repository root:

```bash
python -m jarvis_core
```

Expected visible behavior:

```text
Jarvis AVP-001
jarvis>
```

Ask for the time:

```text
time now
```

or use the exact time command supported by the current planner. Exit with:

```text
exit
```

Expected exit output:

```text
Bye.
```

## Default Runtime Behavior

The default runtime is simulated and offline-safe:

- It does not open network connections.
- It does not create demo devices.
- It does not configure HTTP bindings.
- It does not read or write State Store files.
- It does not load real hardware.
- `device list` starts empty.

Hardware validation uses explicit tools such as:

```powershell
python tools/run_http_led_validation.py --base-url http://<IP_DEL_ESP32>
```

Declarative runtime profiles are loaded only when `--config` is provided. See [Runtime Configuration](CONFIGURATION.md) and [Device State Persistence](STATE_PERSISTENCE.md).

