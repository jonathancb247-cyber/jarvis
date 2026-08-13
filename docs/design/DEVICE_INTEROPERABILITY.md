# Device Interoperability

Status: Future Architecture / Design Guidance

## 1. Vision

JarvisOS should interact with devices according to available protocols and
capabilities rather than requiring membership in a closed commercial ecosystem.

Core principles:

- Protocol over ecosystem.
- Capability over brand.
- Capability over age.

## 2. Compatibility Pipeline

Device support should conceptually progress through:

Discovery
→ Identification
→ Capability Probe
→ Compatibility Assessment
→ Pairing / Trust
→ User Approval
→ Registration

These stages must not be collapsed into a single automatic trust decision.

## 3. Security Invariants

Discovery != Identification.

Identification != Compatibility.

Compatibility != Trust.

Trust != Authorization.

A visible device must not automatically become controllable.

A technically compatible device must not automatically become trusted.

A trusted device must not automatically receive every capability.

## 4. Semantic Capabilities

JarvisOS should reason about semantic capabilities rather than vendor-specific
product names.

Examples:

- power.switch;
- status.read;
- brightness.set;
- temperature.read;
- media.playback;
- presence.read.

Vendor/protocol adapters translate these capabilities into device-specific
operations.

## 5. Protocols

Potential transports/protocols may include:

- HTTP;
- MQTT;
- Matter;
- Zigbee;
- BLE;
- vendor/local APIs;
- future protocol adapters.

Support for one protocol must not force Runtime changes.

## 6. Existing Architectural Direction

HTTP and MQTT demonstrate per-device transport composition.

Future protocols should preserve the same architectural principle:

Runtime
→ semantic device/capability
→ driver boundary
→ protocol adapter
→ physical device

## 7. Discovery

Future discovery must remain bounded.

Topics, addresses, identifiers, or device descriptions discovered from the
environment must be treated as untrusted input.

Discovery should not expose transport internals to AI by default.

## 8. Hardware Reuse

JarvisOS should not ask whether old hardware can run all of JarvisOS.

It should ask what capability the hardware can still provide.

Examples:

- old phone: camera, microphone, display, bridge;
- old laptop: dashboard, voice satellite, compute node;
- Raspberry Pi: gateway, broker, adapter host;
- ESP32: physical sensor/actuator node;
- smartwatch: sensor, interaction surface, personal node.

## 9. Compatibility Case Studies

Useful future reference cases include:

- ESP32 reference nodes;
- commercially available Wi-Fi smart plugs;
- constrained smartwatch ecosystems;
- Wear OS;
- Matter-compatible devices.

These are validation cases, not vendor endorsements.

## 10. Product Goal

JarvisOS should become an interoperability layer capable of extracting useful
capabilities from heterogeneous devices while preserving explicit trust,
authorization, safety, and graceful degradation.