# MQTT ESP32 Validation

Status: Current / Phase 12.4 Physical Validation Guide

This guide validates a real ESP32 as an MQTT-backed JarvisOS device using the existing synchronous request/response MQTT contract.

It does not add product MQTT features, production broker deployment, subscriptions, retained state, LWT, availability topics, retries, discovery, AI, Cognition or Dashboard-specific behavior.

## Scope

Validation topology:

```text
JarvisOS
-> 127.0.0.1:1883
-> Mosquitto
-> local LAN listener
-> ESP32 MQTT LED firmware
-> GPIO2
-> Mosquitto
-> MQTTDeviceDriver
-> DriverResult
-> DeviceStateCoordinator
-> DeviceState
```

JarvisOS uses loopback only. The ESP32 may connect to the same Mosquitto instance through the host's local LAN interface.

No AI provider is required or invoked.

## Reference Firmware

The ESP32 MQTT reference firmware lives at:

```text
examples/mqtt-led/esp32-idf/
```

It is separate from the HTTP reference firmware.

Configure local values with:

```powershell
idf.py menuconfig
```

Then open:

```text
JarvisOS MQTT LED Example
```

Local Wi-Fi values, broker host values and generated `sdkconfig` files must not be committed.

Build and flash:

```powershell
idf.py set-target esp32
idf.py build
idf.py flash monitor
```

## MQTT Contract

Request topic:

```text
jarvis/lab/lamp_1/request
```

Response topic:

```text
jarvis/lab/lamp_1/response
```

Request envelope:

```json
{
  "request_id": "bounded-correlation-id",
  "device_id": "lamp_1",
  "capability": "status.read",
  "operation": "read",
  "parameters": {}
}
```

Successful response:

```json
{
  "request_id": "bounded-correlation-id",
  "ok": true,
  "semantic": {
    "power": false
  },
  "error": null
}
```

Failure response:

```json
{
  "request_id": "bounded-correlation-id",
  "ok": false,
  "semantic": {},
  "error": "operation_not_supported"
}
```

The response envelope is the acknowledgement. There is no separate ACK topic.

Responses must be non-retained.

## Device Mapping

Use the existing semantic device:

```text
lamp_1
```

Capabilities:

```text
status.read
power.switch
```

Safe semantic response keys:

```text
power
```

Topics and broker addresses remain MQTT binding/configuration data. They must not appear in `DeviceCapability`, Runtime API, Dashboard, AI context or semantic `DeviceState`.

## Mosquitto LAN Lab Setup

The Phase 12.3 loopback config is not sufficient by itself because the ESP32 is a separate LAN device.

Use a local copy of:

```text
tools/mosquitto-esp32-lan.example.conf
```

Copy it to an untracked local file and replace `<PC_LAN_IP>` with the host interface address reachable by the ESP32:

```powershell
Copy-Item tools\mosquitto-esp32-lan.example.conf tools\mosquitto-esp32-lan.local.conf
```

Start Mosquitto in the foreground with the local file:

```powershell
mosquitto -c tools\mosquitto-esp32-lan.local.conf -v
```

Requirements:

- keep JarvisOS on `127.0.0.1`;
- expose the broker only to the trusted local LAN interface needed by the ESP32;
- do not use public listeners;
- do not use port forwarding;
- do not use cloud brokers;
- do not commit local addresses;
- do not claim production security.

Anonymous LAN access is acceptable only for this controlled lab gate on a trusted local network. It is not production policy.

## Profile

Copy the example profile:

```powershell
Copy-Item profiles/mqtt-esp32.example.json profiles/mqtt-esp32.local.json
```

The local profile is ignored by Git when named `profiles/*.local.json`.

The profile stores semantic state at:

```text
state/mqtt-esp32.state.json
```

The state file is ignored by Git.

## JarvisOS Validation

Run:

```powershell
python tools\run_mqtt_local_validation.py --config profiles\mqtt-esp32.local.json
```

The runner submits:

```text
device state lamp_1
device read lamp_1 status.read
device apply lamp_1 power.switch state=true
device apply lamp_1 power.switch state=false
```

Manual CLI validation may also use:

```powershell
python -m jarvis_core --config profiles/mqtt-esp32.local.json
```

Then run:

```text
device read lamp_1 status.read
device apply lamp_1 power.switch state=true
device apply lamp_1 power.switch state=false
device state lamp_1
```

## Physical Gate

### Reachable

With the broker running and ESP32 connected:

```text
device read lamp_1 status.read
```

Expected:

- command succeeds;
- `DeviceState` is known/current;
- semantic `power` is returned.

### Physical ON

```text
device apply lamp_1 power.switch state=true
```

Expected:

- JarvisOS reports success;
- user manually confirms GPIO2 LED ON.

### Physical OFF

```text
device apply lamp_1 power.switch state=false
```

Expected:

- JarvisOS reports success;
- user manually confirms GPIO2 LED OFF.

### Persistence And Restart

1. Reach a known state.
2. Shut JarvisOS down cleanly.
3. Restart with the same local profile.
4. Confirm restored state is stale/not current.
5. Run an explicit `status.read`.
6. Confirm state becomes known/current.

### ESP32 Disconnect

1. Physically disconnect or power off the ESP32.
2. Do not change JarvisOS configuration.
3. Run:

   ```text
   device read lamp_1 status.read
   ```

Expected:

- command fails safely;
- prior semantic properties are preserved;
- state becomes stale/not current;
- no broker topic, address, socket error, raw exception or transport detail leaks into semantic state or public projection.

### Reconnect

1. Restore ESP32 reachability.
2. Run:

   ```text
   device read lamp_1 status.read
   ```

Expected:

- command succeeds;
- state becomes known/current;
- semantic `power` reflects the physical device.

## Evidence Package

Capture:

- Mosquitto startup summary without personal addresses;
- ESP32 firmware build/flash success;
- first reachable read result;
- power on software result;
- manual LED on confirmation;
- power off software result;
- manual LED off confirmation;
- shutdown/restart stale evidence;
- disconnected read safe failure;
- reconnect read recovery;
- confirmation no transport details entered semantic state or public responses.

Do not record raw secrets, local addresses, Wi-Fi credentials, raw packet captures or private network details.

## Non-Goals

Phase 12.4 does not implement:

- production MQTT deployment;
- MQTT authentication;
- MQTT TLS credentials;
- no retained state;
- retained state ingestion;
- no LWT;
- LWT or availability topics;
- async subscriptions;
- no polling;
- background polling;
- automatic offline detection;
- no discovery;
- automatic discovery;
- Dashboard MQTT UI;
- MQTT Runtime API routes;
- AI-provider behavior;
- Cognition integration.
