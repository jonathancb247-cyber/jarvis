# First Device

Status: Current / Simulated And Hardware-Validated Paths

JarvisOS currently supports two practical ways to explore devices:

- Simulated discovery and onboarding.
- A hardware-validated ESP32 + ESP-IDF HTTP LED example.

## Path 1: Simulated Device

Run JarvisOS:

```bash
python -m jarvis_core
```

Discover simulated candidates:

```text
device discover
```

Onboard a candidate from the latest discovery result:

```text
device onboard <candidate_id> as lamp_1
```

Inspect the catalog:

```text
device list
device info lamp_1
device state lamp_1
```

Simulated devices and candidates are in-memory. They disappear when the runtime stops.

## Declarative Config Path

JarvisOS can also load Devices and HTTP bindings from an explicit JSON profile:

```powershell
python -m jarvis_core --config profiles/http-lab.local.json
```

See [Runtime Configuration](CONFIGURATION.md). This recreates configured Devices and bindings at startup.

If the profile enables `state_store_path`, JarvisOS also restores the last semantic `DeviceState` as stale. See [Device State Persistence](STATE_PERSISTENCE.md).

For the full profile-based ESP32 validation and restart flow, see [HTTP Profile Validation](HTTP_PROFILE_VALIDATION.md).

## Path 2: Hardware-Validated ESP32 LED

The first hardware-validated example uses:

- ESP32 + ESP-IDF.
- Wi-Fi on a local network.
- HTTP local transport.
- Built-in LED on GPIO2 for the validated board.
- `power.switch` and `status.read`.

Start the validation runtime:

```powershell
python tools/run_http_led_validation.py --base-url http://<IP_DEL_ESP32>
```

Then use:

```text
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
device state lamp_1
device apply lamp_1 power.switch state=false
```

Read the full platform guide:

- [ESP32 + ESP-IDF](../platforms/ESP32_ESP_IDF.md)
- [HTTP LED example](../../examples/http-led/README.md)

