# JarvisOS Dashboard

Status: Current / Experimental

The JarvisOS Dashboard is an optional local browser UI for the localhost Runtime API. It is not part of the default runtime and it is not required for the CLI or AI Adapter.

Start it explicitly:

```bash
python -m jarvis_core.dashboard --config profiles/http-lab.local.json
```

The Dashboard serves fixed offline assets and uses same-origin REST calls to:

- `GET /api/v1/health`
- `GET /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `GET /api/v1/devices/{device_id}/capabilities`
- `GET /api/v1/devices/{device_id}/state`
- `POST /api/v1/commands`

It displays only data returned by the Runtime API. It does not display fake capabilities, history, online status, AI state, bindings, URLs, IP addresses, config paths, State Store paths, credentials, logs, or raw payloads.

See:

- [Usage](USAGE.md)
- [Security](SECURITY.md)
- [Runtime API](../api/README.md)

Not implemented:

- AI chat;
- authentication or authorization;
- LAN or public internet access;
- WebSocket or Server-Sent Events;
- external frontend frameworks;
- Node.js or a build system;
- profile, binding, State Store, or secrets editing.

