# Security Guidelines

Status: Current / Experimental Local Device Security Guidance

## Current State

The first real JarvisOS device transport is HTTP local and experimental.

It is not production secure:

- No authentication.
- No TLS.
- No public internet exposure.
- No secrets store.
- No persistent trust.
- No authorization engine.

## Required Rules

- Do not expose device nodes to the public internet.
- Use a controlled local network.
- Do not store passwords in `Device.metadata`.
- Do not store tokens in device bindings.
- Do not log sensitive full URLs.
- Do not log raw payloads.
- Do not return stack traces to adapters.
- Do not auto-register devices.
- Do not auto-onboard devices.
- Do not run background discovery.
- Use mandatory timeouts.
- Limit payload size.
- Validate JSON.
- Use controlled endpoints.

## Future Work

These are Future / Not Implemented:

- Authentication.
- TLS.
- Secrets Boundary.
- Authorization.
- Persistent trust.
- Revocation.
- Production-grade endpoint security.

