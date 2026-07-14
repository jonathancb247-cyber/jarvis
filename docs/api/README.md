# JarvisOS Runtime API

Status: Current / Experimental

The Runtime API is an optional localhost-only REST/JSON adapter for inspecting and controlling JarvisOS through safe API contracts. It is not the Dashboard and it is not enabled by the default CLI runtime.

Start it explicitly:

```bash
python -m jarvis_core.api --config profiles/http-lab.local.json
```

The API submits canonical JarvisOS command text through the existing Runtime-owned adapter boundary:

```text
HTTP request
-> RuntimeApiAdapter
-> Runtime.handle_adapter_input(...)
-> Planner
-> Command
-> Runtime
-> CapabilityResult
-> safe JSON response
```

The API also exposes detached semantic projections for health, devices, capabilities, and state. It does not expose live Runtime objects, registries, binding stores, drivers, State Store paths, raw payloads, exceptions, stack traces, credentials, URLs, or IP addresses.

See:

- [Routes](ROUTES.md)
- [Security](SECURITY.md)

Not implemented:

- Dashboard;
- authentication or authorization;
- LAN or public internet access;
- WebSocket or Server-Sent Events;
- async Runtime;
- profile, binding, State Store, or secrets editing.
