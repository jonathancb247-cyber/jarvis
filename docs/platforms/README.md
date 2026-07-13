# Platform Guides

Status: Current / Platform Documentation Index

Each platform guide states whether support is current, planned, future reference, or not supported.

Allowed status labels:

- `Current / Hardware Validated`
- `Current / Software Validated`
- `Current / Host Supported`
- `Planned`
- `Future Reference`
- `Partial / Future`
- `Not Supported`

JarvisOS keeps device semantics transport-agnostic. A `Device` and its `DeviceCapability` values do not contain URLs, GPIO numbers, serial ports, MQTT topics, credentials, or HTTP paths.

## Guides

| Platform | Status | Primary role |
|---|---|---|
| [ESP32 + ESP-IDF](ESP32_ESP_IDF.md) | Current / Hardware Validated | HTTP local node |
| [ESP32 Arduino](ESP32_ARDUINO.md) | Planned | HTTP local node |
| [ESP8266](ESP8266.md) | Planned | HTTP local node |
| [Arduino](ARDUINO.md) | Future Reference | Serial/USB node |
| [STM32](STM32.md) | Future Reference | USB CDC, UART, or HTTP node |
| [Raspberry Pi](RASPBERRY_PI.md) | Partial / Future | Host, HTTP node, future GPIO |
| [Linux PC](LINUX_PC.md) | Current / Host Supported | Host |
| [Windows PC](WINDOWS_PC.md) | Current / Host Supported | Host and development |
| [Android](ANDROID.md) | Future Reference | Bridge or node |

