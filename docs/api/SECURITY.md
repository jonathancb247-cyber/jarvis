# Runtime API Security

Status: Current / Experimental

The Runtime API is local-only in Phase 11.2.

Default bind address:

```text
127.0.0.1
```

Do not expose this API to a LAN or the public internet. LAN access requires a future authentication and authorization design.

## Current Limits

- localhost only;
- JSON requests only for command execution;
- maximum request body: 16 KiB;
- maximum canonical command length: 512 characters;
- unknown JSON fields rejected;
- duplicate JSON keys rejected;
- unsupported methods rejected;
- no wildcard CORS headers;
- no redirects;
- no static file serving;
- no shell, filesystem, profile editing, binding editing, State Store editing, or secrets endpoints.

## Privacy

The API must not expose:

- bindings;
- URLs or IP addresses;
- ports;
- headers;
- credentials;
- tokens;
- certificates;
- State Store paths;
- raw configuration;
- raw State Store contents;
- raw DriverResult;
- DeviceExecutionResult;
- raw HTTP payloads;
- exceptions;
- stack traces;
- RuntimeContext;
- EventBus;
- AI provider prompts or responses.

## Command Execution

Command requests enter through `Runtime.handle_adapter_input(...)`. The API does not create `Command` objects directly, call Drivers, call DeviceCommandRouter, mutate DeviceRegistry, or write State Store.

## Concurrency

The standard-library server may handle HTTP requests in separate threads. Runtime command execution is protected by an adapter-owned lock in the MVP. This does not define concurrent mutation semantics.

## Not Implemented

- authentication;
- authorization;
- sessions;
- API tokens;
- TLS;
- LAN mode;
- WebSocket;
- Server-Sent Events;
- async Runtime;
- background workers.
