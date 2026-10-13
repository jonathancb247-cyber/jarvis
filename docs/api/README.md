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

## Interaction-only mode

The API can optionally expose an authenticated, strictly **non-executing**
interaction endpoint in explicit interaction-only mode:

```bash
python -m jarvis_core.api --config profiles/http-lab.local.json \
  --interaction-only \
  --interaction-provider-model gemma-2b
```

```text
HTTP request (Bearer token)
-> RuntimeApiAdapter
-> LocalInteractionService
-> SafeContextBuilder
-> handle_interaction / decide_understanding
-> deterministic LocalUnderstandingDecision
-> safe JSON response (commands_executed = false)
```

In this mode `POST /api/v1/commands` is disabled, the read-only projections stay
available, and a bearer token from `JARVIS_API_INTERACTION_TOKEN` is required.
The endpoint reuses the existing interaction boundary and never calls Runtime,
Drivers, the Planner, or the ExecutionGate. See [Routes](ROUTES.md) for the exact
contract.

See:

- [Routes](ROUTES.md)
- [Security](SECURITY.md)

Not implemented:

- Dashboard;
- authentication or authorization for the command and projection routes;
- LAN or public internet access;
- WebSocket or Server-Sent Events;
- async Runtime;
- profile, binding, State Store, or secrets editing.
