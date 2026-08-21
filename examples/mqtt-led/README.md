# MQTT LED Example

Status: Current / Experimental Reference Example

This example shows a minimal ESP32 + ESP-IDF device node controlled by JarvisOS through the experimental MQTT request/response protocol.

It is separate from the hardware-validated HTTP LED example so the HTTP reference firmware remains unchanged.

## Architecture

```text
JarvisOS CLI
-> Planner
-> Runtime
-> DeviceRuntimeCapability
-> DeviceCommandRouter
-> MQTTDeviceDriver
-> PahoMQTTClient
-> Mosquitto
-> ESP32 MQTT LED firmware
-> GPIO2
-> Mosquitto
-> MQTTDeviceDriver
-> DriverResult
-> DeviceStateCoordinator
-> DeviceState
-> CapabilityResult
```

## Hardware

- ESP32 classic / DevKit-style board.
- Built-in LED on GPIO2 for the reference board.
- 2.4 GHz Wi-Fi local network.
- A host running Mosquitto and JarvisOS on the same trusted local LAN.

## Firmware

ESP-IDF firmware:

```text
examples/mqtt-led/esp32-idf/
```

Configure local values with:

```text
idf.py menuconfig
-> JarvisOS MQTT LED Example
```

Do not commit generated `sdkconfig` files, Wi-Fi credentials, broker host values, or local validation output.

## Protocol

The firmware subscribes only to:

```text
jarvis/lab/lamp_1/request
```

The firmware publishes non-retained responses to:

```text
jarvis/lab/lamp_1/response
```

Supported capabilities:

- `power.switch`
- `status.read`

The response envelope is the acknowledgement. There is no separate ACK topic, no retained state, no LWT, no availability topic, no polling and no discovery behavior.

## JarvisOS Runtime

Copy the example profile and edit only local, untracked files:

```powershell
Copy-Item profiles/mqtt-esp32.example.json profiles/mqtt-esp32.local.json
python tools/run_mqtt_local_validation.py --config profiles\mqtt-esp32.local.json
```

JarvisOS still connects to Mosquitto through `127.0.0.1`. The ESP32 connects to the same broker through the host's local LAN address.

For the full physical validation workflow, see [MQTT ESP32 Validation](../../docs/drivers/MQTT_ESP32_VALIDATION.md).

## Commands

```text
device read lamp_1 status.read
device apply lamp_1 power.switch state=true
device apply lamp_1 power.switch state=false
device state lamp_1
```

## Validation

Expected behavior:

- `device read` returns the ESP32-reported `power` state.
- `state=true` turns GPIO2 on.
- `state=false` turns GPIO2 off.
- failed explicit reads after a prior known state preserve semantic properties and make state stale.
- reconnect plus explicit read restores known/current state.

Physical LED on/off evidence must be confirmed manually.

## Limitations

- Experimental.
- Local LAN validation only.
- No authentication.
- No TLS.
- No retained messages.
- No LWT or availability topic.
- No automatic discovery.
- No production broker deployment.
- GPIO2 is specific to the reference board.
