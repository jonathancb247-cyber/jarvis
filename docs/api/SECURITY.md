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
- JSON requests only for command execution and interactions;
- maximum request body: 16 KiB;
- maximum canonical command length: 512 characters;
- maximum interaction message length: 4096 characters;
- unknown JSON fields rejected;
- duplicate JSON keys rejected;
- `Transfer-Encoding` rejected; exactly one `Content-Length` required;
- `Content-Length` must be ASCII digits only (signs, separators, hex, whitespace and non-ASCII digits are rejected) and the body is read to exactly that length, so oversized bodies are rejected before being read;
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

Open connections are bounded globally (default 16): a connection is admitted
before any request byte is read, and over-capacity connections are rejected
immediately with `api_server_busy` (HTTP 503) and closed instead of spawning
unbounded threads.

Each request is read under one absolute time budget (default 5 seconds) covering
both headers and body, so a client that trickles bytes slowly cannot extend the
total read time. Requests whose body is not delivered within the budget are
rejected and the connection is closed.

Interaction-only turns are additionally bounded by a non-blocking semaphore;
when capacity is exhausted the endpoint fails fast with `api_interaction_busy`
instead of queuing without limit.

## Interaction-only mode authentication

The authenticated interaction endpoint is only mounted in explicit
interaction-only mode. It requires a constant-time Bearer token read from the
environment variable named by `--interaction-token-env` (default
`JARVIS_API_INTERACTION_TOKEN`). The token is never logged or projected, and the
process fails to start when it is unset, blank, shorter than 16 characters, or
not printable ASCII without whitespace (fail closed).

The interaction route is authenticated before its request body is read.
Malformed or non-ASCII `Authorization` headers are rejected with HTTP 401 and
never surface as an internal error.

The interaction route reuses the existing non-executing interaction boundary. It
builds the safe context and permissions server-side from the injected device
registry and never calls Runtime, Drivers, the Planner, or the ExecutionGate.
`commands_executed` is always false.

The command and read-only projection routes remain unauthenticated and are not
intended for any non-loopback exposure. Do not expose this API to a LAN or the
public internet.

## Not Implemented

- authentication or authorization for the command and projection routes;
- authorization or per-capability access control for interactions;
- sessions;
- TLS;
- LAN mode;
- WebSocket;
- Server-Sent Events;
- async Runtime;
- background workers.
