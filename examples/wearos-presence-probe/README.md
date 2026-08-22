# Wear OS Presence Probe

Status: validation-only sample.

This sample is a minimal Pixel Watch / Wear OS probe for the Wearable Phase 1
real hardware validation gate. It is not a JarvisOS watch app.

It sends a bounded local HTTP heartbeat while the validation screen is active:

```json
{"state":"connected","wearable_id":"pixel_watch_probe"}
```

The heartbeat proves only that a known Wear OS probe appears connected to the
local wearable boundary. It does not prove user presence, watch wearing,
identity, wakefulness, availability, health, or location.

## Local Configuration

Create `local.properties` in this directory or pass the property on the Gradle
command line:

```properties
jarvis.receiverUrl=http://YOUR_PC_LAN_IP:8766/wearable/presence
```

Do not commit local IP addresses, Wi-Fi details, credentials, or generated
artifacts.

## Build

```powershell
gradle :app:assembleDebug
```

## Validation Receiver

Start the PC-side validation receiver from the repository root:

```powershell
python tools/run_wearable_presence_validation.py --host YOUR_PC_LAN_IP --port 8766
```

This receiver is local/lab-only. It is not the Runtime API and does not expose
Runtime, Planner, Drivers, DeviceState, API, Dashboard, Voice, AI, persistence,
providers, notifications, health data, or location.

## Manual Hardware Gate

1. Enable Developer options and Wireless debugging on the Pixel Watch.
2. Pair ADB:
   `adb pair WATCH_IP:PAIRING_PORT`
3. Connect ADB:
   `adb connect WATCH_IP:CONNECTION_PORT`
4. Install the debug APK.
5. Start the PC receiver.
6. Launch the watch probe.
7. Observe `connected`.
8. Stop the probe or disconnect watch Wi-Fi.
9. Observe `stale`, `unknown`, or explicit `disconnected` according to receiver
   state.
10. Restore the probe and observe `connected` again.

