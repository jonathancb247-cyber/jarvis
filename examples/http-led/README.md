# HTTP LED Example

Status: Current / Hardware Validated

This example shows a minimal ESP32 + ESP-IDF device node controlled by JarvisOS through the experimental local HTTP protocol.

## Architecture

```text
JarvisOS CLI
-> Planner
-> Runtime
-> DeviceRuntimeCapability
-> DeviceCommandRouter
-> HttpDeviceDriver
-> ESP32
-> GPIO2
-> DriverResult
-> DeviceStateCoordinator
-> DeviceState
-> CapabilityResult
```

## Hardware

- ESP32 classic / DevKit-style board.
- Built-in LED on GPIO2 for the validated board.
- 2.4 GHz Wi-Fi local network.

## Firmware

ESP-IDF firmware:

```text
examples/http-led/esp32-idf/
```

Configure Wi-Fi with:

```text
idf.py menuconfig
-> JarvisOS HTTP LED Example
-> Wi-Fi SSID
-> Wi-Fi Password
```

Do not commit credentials.

## Protocol

The firmware implements:

- `POST /device/apply`
- `POST /device/read`

Capabilities:

- `power.switch`
- `status.read`

Protocol examples:

- [apply-on.json](protocol-examples/apply-on.json)
- [apply-off.json](protocol-examples/apply-off.json)
- [read-status.json](protocol-examples/read-status.json)
- [success-on.json](protocol-examples/success-on.json)
- [success-off.json](protocol-examples/success-off.json)
- [error-operation-not-supported.json](protocol-examples/error-operation-not-supported.json)

## JarvisOS Runtime

Start the explicit hardware validation runtime:

```powershell
python tools/run_http_led_validation.py --base-url http://<IP_DEL_ESP32>
```

The default runtime does not create `lamp_1`, does not configure an HTTP binding, and does not open network connections.

## Commands

```text
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
device state lamp_1
device apply lamp_1 power.switch state=false
device read lamp_1 status.read
device state lamp_1
```

## Validation

Expected behavior:

- `state=true` turns the LED on.
- `device read` returns the ESP32-reported state.
- `device state lamp_1` reflects semantic state after successful operations.
- `state=false` turns the LED off.

## Errors

If the ESP32 is unavailable, JarvisOS should return a safe error without exposing URLs, IPs, raw payloads, headers, exception text, or stack traces.

## Limitations

- Experimental.
- Local network only.
- No authentication.
- No TLS.
- No persistence.
- Manual IP.
- No real discovery.
- No real onboarding.
- Not production secure.

