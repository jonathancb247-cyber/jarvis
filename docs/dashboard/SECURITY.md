# Dashboard Security

Status: Current / Experimental

The Dashboard is local-only in Phase 11.3.

Default bind address:

```text
127.0.0.1
```

Do not expose this Dashboard to a LAN or the public internet. LAN access requires a future authentication and authorization design.

## Current Limits

- localhost only;
- fixed package static assets only;
- no directory listing;
- no arbitrary file serving;
- no path traversal;
- no remote assets;
- no external CDN dependencies;
- no wildcard CORS headers;
- no WebSocket or Server-Sent Events;
- no browser credential storage;
- no retries or background command execution.

## UI Safety

The Dashboard treats API strings as untrusted text.

Rules:

- render dynamic data with `textContent`;
- URL-encode device IDs for API paths;
- do not use untrusted `innerHTML`;
- do not execute JavaScript from device data;
- do not use metadata-driven UI;
- do not send automatic mutation commands on page load;
- require an explicit click for actions;
- show a lightweight confirmation before mutation controls.

## Privacy

The Dashboard must not display:

- bindings;
- URLs or IP addresses;
- ports;
- headers;
- credentials;
- State Store paths;
- raw configuration;
- raw DriverResult or DeviceExecutionResult;
- raw device HTTP payloads;
- exceptions;
- stack traces;
- RuntimeContext;
- EventBus;
- AI provider prompts or responses.
