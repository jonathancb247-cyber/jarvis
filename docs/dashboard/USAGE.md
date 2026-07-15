# Dashboard Usage

Status: Current / Experimental

## Start

Create a local profile from `profiles/http-lab.example.json`, then run:

```bash
python -m jarvis_core.dashboard --config profiles/http-lab.local.json
```

The server binds to `127.0.0.1` by default and prints a local URL.

## Screens

Overview:

- runtime status;
- prototype label;
- device count;
- persistence status;
- known, stale and unknown counts;
- API connection state.

Devices:

- device ID;
- name;
- type;
- status;
- current/not current;
- capability count;
- client-side search.

Device Detail:

- safe device information;
- formal capabilities;
- semantic state;
- generated primitive controls when supported.

Command Console:

- one canonical JarvisOS command input;
- safe success or error result;
- bounded in-memory session history.

## State Semantics

`known` means the API reports the state as current.

`unknown` means no current semantic state is known.

`stale` means the last persisted state and does not confirm current device availability.

## Capability Controls

The Dashboard generates controls only from formal capabilities returned by the API.

For the HTTP LED profile:

- `power.switch` can produce On/Off commands;
- `status.read` can produce a read command.

Unsupported capability shapes are displayed as details instead of invented controls.

