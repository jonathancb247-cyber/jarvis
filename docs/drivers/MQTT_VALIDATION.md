# MQTT Local Broker Validation

Status: Current / Experimental Local Integration Gate

Phase 12.3 validates the existing MQTT request/response driver through a real
local Mosquitto broker and a tiny local simulated MQTT lamp. It does not require
ESP32 hardware and does not add MQTT product features.

## Scope

The validation topology is:

```text
JarvisOS
-> MQTTDeviceDriver
-> PahoMQTTClient
-> Mosquitto on 127.0.0.1
-> local simulated lamp
-> Mosquitto
-> PahoMQTTClient
-> MQTTDeviceDriver
-> DriverResult
-> Runtime / DeviceState
```

The simulated lamp is a validation tool only. It is not a device simulator
framework and must not become product architecture.

No AI provider is required or invoked by this validation.

## Dependencies

JarvisOS uses `paho-mqtt==2.1.0` for the local real-client adapter.

Mosquitto is an external local broker. It is not a Python dependency and is not
required for normal unit tests.

## Loopback Broker Policy

Use the repository validation config:

```text
tools/mosquitto-loopback.conf
```

It binds only to loopback:

```text
listener 1883 127.0.0.1
allow_anonymous true
persistence false
```

Anonymous access is allowed only for this loopback-only validation. Do not use
anonymous access on LAN or public listeners.

Do not use:

- `0.0.0.0`;
- LAN listeners;
- port forwarding;
- ngrok;
- cloud brokers;
- remote administration;
- credentials committed to the repository.

## Startup

Install Mosquitto from the official project distribution if it is not already
available on the host.

Run the broker in the foreground when possible:

```powershell
mosquitto -c tools\mosquitto-loopback.conf -v
```

If the official Windows installer starts an existing Mosquitto service and it
is already bound only to loopback, that local service is acceptable for this
validation. Do not expose the broker to LAN/public interfaces.

Start the simulated lamp in another terminal:

```powershell
python tools\mqtt_simulated_lamp.py
```

Run the JarvisOS validation in another terminal:

```powershell
python tools\run_mqtt_local_validation.py --config profiles\mqtt-lab.example.json
```

## Expected Commands

The validation runner exercises:

```text
device read lamp_1 status.read
device apply lamp_1 power.switch state=true
device apply lamp_1 power.switch state=false
```

No physical LED claim is allowed. The simulated lamp maintains only ephemeral
process-local boolean state.

## Persistence

The profile stores semantic state at:

```text
state/mqtt-lab.state.json
```

The state file is ignored by Git. Restored state becomes `stale`; broker
connectivity does not make restored state current.

## Failure Checks

Manual validation should cover:

- broker unavailable;
- broker stopped during operation;
- simulator unavailable;
- no response;
- wrong `request_id`;
- delayed response;
- duplicate response;
- malformed response;
- recovery after broker and simulator restart;
- clean shutdown.

Phase 12.3 was validated against Mosquitto 2.1.2 on loopback with
`paho-mqtt==2.1.0`. The Windows service could not be stopped from the
non-admin validation session, so broker stop/restart remains admin-blocked;
normal broker operation, simulator failure/recovery, and broker-unavailable
software paths were validated safely.

JarvisOS must accept only an exact matching in-window response. There is no
automatic mutation retry and no background recovery loop.

## Not Implemented

Phase 12.3 does not implement:

- ESP32 MQTT physical validation;
- MQTT subscriptions;
- retained-message state ingestion;
- availability/LWT state semantics;
- MQTT authentication or TLS credentials;
- cloud broker support;
- Dashboard MQTT UI;
- MQTT Runtime API routes;
- AI-provider behavior.

Phase 12.4 is the separate ESP32 MQTT reference node implementation and
physical validation gate.

The Phase 12.4 ESP32-specific workflow is documented separately in
[MQTT ESP32 Validation](MQTT_ESP32_VALIDATION.md).
