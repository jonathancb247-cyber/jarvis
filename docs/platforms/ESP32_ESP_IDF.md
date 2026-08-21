# ESP32 + ESP-IDF Integration

Status: Current / Hardware Validated

## Overview

ESP32 + ESP-IDF is the first hardware-validated JarvisOS device platform. The validated example exposes a local HTTP device node that controls the built-in LED on GPIO2.

## Current Support

Validated:

- ESP32-WROOM-32 / DevKit-style board.
- ESP-IDF.
- Wi-Fi local network.
- HTTP local protocol.
- `POST /device/apply`.
- `POST /device/read`.
- `power.switch`.
- `status.read`.
- GPIO2 built-in LED on the tested board.

## Possible Architectures

```text
JarvisOS Host
-> HTTP local
-> ESP32
-> GPIO / Peripheral
```

You can use the same pattern for:

- LED.
- Relay.
- Lamp.
- Sensor.
- Node.
- Controller.

## Requirements

- ESP32 classic / DevKit-style board.
- ESP-IDF.
- VS Code ESP-IDF extension or ESP-IDF command line.
- 2.4 GHz Wi-Fi.
- PC, Raspberry Pi, Linux host, or Windows host running JarvisOS.

## Recommended Transport

HTTP local is the current hardware-validated transport for ESP32 + ESP-IDF.
MQTT request/response has a separate experimental reference example for Phase
12.4 physical validation.

## Setup

1. Open the example project:

   ```text
   examples/http-led/esp32-idf/
   ```

2. Set target:

   ```powershell
   idf.py set-target esp32
   ```

3. Configure Wi-Fi:

   ```text
   idf.py menuconfig
   -> JarvisOS HTTP LED Example
   -> Wi-Fi SSID
   -> Wi-Fi Password
   ```

Do not commit Wi-Fi credentials.

## Project

The example uses:

- `esp_wifi`.
- `esp_http_server`.
- `esp_event`.
- `esp_netif`.
- `nvs_flash`.
- `driver/gpio`.
- `cJSON`.

The validated LED pin is defined by:

```c
#define JARVIS_LED_GPIO GPIO_NUM_2
```

Other boards may use a different built-in LED GPIO.

## Firmware

The firmware lives at:

```text
examples/http-led/esp32-idf/
```

Main responsibilities:

- Wi-Fi initialization.
- GPIO initialization.
- Apply handler.
- Read handler.
- JSON response generation.
- HTTP server start.

## Direct Test

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://<IP>/device/apply" `
  -ContentType "application/json" `
  -Body '{"capability":"power.switch","parameters":{"state":"true"}}'
```

## JarvisOS Configuration

Use the profile-based runtime for configuration, HTTP binding reconstruction, and DeviceState persistence:

```powershell
Copy-Item profiles/http-lab.example.json profiles/http-lab.local.json
python -m jarvis_core --config profiles/http-lab.local.json
```

Edit `profiles/http-lab.local.json` so `base_url` points to the ESP32.

The manual validation helper remains available for direct driver checks without config/state persistence:

```powershell
python tools/run_http_led_validation.py --base-url http://<IP>
```

See [Runtime Configuration](../getting-started/CONFIGURATION.md), [Device State Persistence](../getting-started/STATE_PERSISTENCE.md), and [HTTP Profile Validation](../getting-started/HTTP_PROFILE_VALIDATION.md). The State Store persists only semantic `DeviceState` and restores it as stale.

## MQTT Reference Example

The MQTT request/response reference firmware lives at:

```text
examples/mqtt-led/esp32-idf/
```

It uses the same `lamp_1`, `power.switch`, `status.read` and GPIO2 LED semantics
with Mosquitto as a local LAN broker. JarvisOS still connects to the broker over
`127.0.0.1`; the ESP32 connects to the host's local LAN listener. See
[MQTT ESP32 Validation](../drivers/MQTT_ESP32_VALIDATION.md).

## Example Commands

```text
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
device state lamp_1
device apply lamp_1 power.switch state=false
```

## Security

This is an experimental local-network example. It does not implement authentication, TLS, authorization, or persistent trust. Do not expose it to the public internet.

## Limitations

- No authentication.
- No TLS.
- Experimental DeviceState persistence only.
- Manual IP.
- No real discovery.
- No real onboarding.
- GPIO2 is specific to the validated board.
- Experimental protocol.

## Troubleshooting

See [Troubleshooting](../device-integration/TROUBLESHOOTING.md).

## Future Work

- Authentication.
- TLS.
- Discovery.
- Persistent configuration.
- Additional capabilities.

