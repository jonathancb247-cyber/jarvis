# ESP32 ESP-IDF MQTT LED Firmware

Status: Current / Experimental Reference Firmware

This ESP-IDF project implements the JarvisOS experimental MQTT request/response protocol for a GPIO2 LED.

It is intended for Phase 12.4 physical validation only and is not a generic ESP32 JarvisOS SDK.

## Configure

```powershell
idf.py menuconfig
```

Then open:

```text
JarvisOS MQTT LED Example
```

Set local Wi-Fi and broker values there. Do not commit generated `sdkconfig` files or local credentials.

## Build And Flash

```powershell
idf.py set-target esp32
idf.py build
idf.py flash monitor
```

## MQTT Topics

Request:

```text
jarvis/lab/lamp_1/request
```

Response:

```text
jarvis/lab/lamp_1/response
```

Responses are published with `retain=false`.

## Supported Capabilities

- `power.switch`
- `status.read`

## JarvisOS Validation

Use an untracked local profile:

```powershell
Copy-Item profiles/mqtt-esp32.example.json profiles/mqtt-esp32.local.json
python tools/run_mqtt_local_validation.py --config profiles\mqtt-esp32.local.json
```

The full manual gate is documented in [MQTT ESP32 Validation](../../../docs/drivers/MQTT_ESP32_VALIDATION.md).

## Limitations

- No authentication.
- No TLS.
- No retained messages.
- No LWT.
- No availability topic.
- No persistence.
- No automatic discovery.
- Experimental local-network validation only.
