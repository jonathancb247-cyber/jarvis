# JarvisOS Device Integration Guide

Status: Current / Experimental Device Integration

This guide explains how to connect a device, board, or technical node to JarvisOS.

GitHub is the source of truth for implementation, protocols, examples and platform integration guides. Notion summarizes architecture, roadmap and decisions, but must not duplicate exact code.

## What Device Integration Means

To integrate a device, JarvisOS needs:

- A `Device` registered in the in-memory catalog.
- `DeviceCapability` descriptors that explain what the device can do.
- A transport-specific binding that explains how JarvisOS reaches the device.
- A driver that converts device operations into technical communication.
- A device-side protocol implementation that returns observations.

The device does not receive `Command` objects. Commands are internal to JarvisOS.

## Current Transport

| Transport | Status | Notes |
|---|---|---|
| HTTP local | Current / Experimental | First real driver, validated with ESP32 + ESP-IDF |
| Serial/USB | Future Reference | No official driver yet |
| MQTT | Future Reference | Not implemented |
| GPIO local | Future Reference | Not implemented |
| BLE | Future Reference | Not implemented |

## What Do You Want To Integrate?

```text
What do you want to integrate?
|
+-- ESP32 with ESP-IDF
|   +-- HTTP local - Hardware Validated
|
+-- ESP32 with Arduino Framework
|   +-- HTTP local - Planned
|
+-- ESP8266
|   +-- HTTP local - Planned
|
+-- Arduino Uno
|   +-- Serial/USB - Future
|
+-- STM32
|   +-- USB CDC - Future
|   +-- UART Bridge - Future
|   +-- HTTP with external networking - Future
|
+-- Raspberry Pi
|   +-- JarvisOS Host
|   +-- HTTP Node
|   +-- GPIO local - Future
|
+-- Linux PC
|   +-- Host / Node / Adapter
|
+-- Windows PC
|   +-- Host / Development
|
+-- Android
    +-- Bridge / Node - Future
```

## Platform Status

| Platform | Transport | Status | Hardware validated |
|---|---|---|---|
| ESP32 + ESP-IDF | HTTP local | Current / Experimental | Yes |
| ESP32 Arduino | HTTP local | Planned | No |
| ESP8266 | HTTP local | Planned | No |
| Arduino Uno | Serial/USB | Future | No |
| STM32 | USB CDC / UART / HTTP | Future | No |
| Raspberry Pi | Host / HTTP / GPIO | Partial / Future | No |
| Linux PC | Host | Current | Yes |
| Windows PC | Host | Current | Yes |
| Android | Bridge | Future | No |

## Start Here

- [Installation](../getting-started/INSTALLATION.md)
- [First run](../getting-started/FIRST_RUN.md)
- [First device](../getting-started/FIRST_DEVICE.md)
- [Device protocol](DEVICE_PROTOCOL.md)
- [Capability model](CAPABILITY_MODEL.md)
- [Driver development](DRIVER_DEVELOPMENT.md)
- [Security guidelines](SECURITY_GUIDELINES.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Platform guides](../platforms/README.md)
- [Examples](../examples/README.md)

