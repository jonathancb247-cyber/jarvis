# ESP32 Arduino Integration

Status: Planned

## Overview

ESP32 Arduino support is planned as a future HTTP local node option.

## Current Support

No official ESP32 Arduino firmware is validated yet.

## Possible Architectures

```text
JarvisOS Host
-> HTTP local
-> ESP32 Arduino firmware
-> GPIO / Peripheral
```

## Requirements

Future work will likely require:

- ESP32 board.
- Arduino framework.
- Wi-Fi library.
- HTTP server library.
- JSON handling.

## Recommended Transport

HTTP local is the likely transport, matching the ESP-IDF example.

## Setup

Not implemented.

## JarvisOS Configuration

Not implemented.

## Example Commands

Likely future commands:

```text
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
```

## Security

Future ESP32 Arduino support must follow the same local-network security guidelines as the ESP-IDF example.

## Limitations

- No official firmware.
- Not hardware validated.
- No Arduino-specific guide yet.

## Troubleshooting

Use the ESP-IDF guide only for the currently validated firmware.

## Future Work

- Official Arduino firmware.
- Validation on common boards.
- Documentation for Arduino IDE and PlatformIO.

