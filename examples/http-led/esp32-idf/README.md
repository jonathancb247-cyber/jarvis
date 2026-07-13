# ESP32 ESP-IDF HTTP LED Firmware

Status: Current / Hardware Validated Example

This ESP-IDF project implements the JarvisOS experimental local HTTP protocol for a GPIO2 LED.

## Configure Wi-Fi

```powershell
idf.py menuconfig
```

Then open:

```text
JarvisOS HTTP LED Example
-> Wi-Fi SSID
-> Wi-Fi Password
```

Do not commit Wi-Fi credentials.

## Build And Flash

```powershell
idf.py set-target esp32
idf.py build
idf.py flash monitor
```

## Endpoints

- `POST /device/apply`
- `POST /device/read`

## Supported Capabilities

- `power.switch`
- `status.read`

## JarvisOS Validation

```powershell
python tools/run_http_led_validation.py --base-url http://<IP_DEL_ESP32>
```

Then run:

```text
device apply lamp_1 power.switch state=true
device read lamp_1 status.read
device state lamp_1
device apply lamp_1 power.switch state=false
```

## Limitations

- No authentication.
- No TLS.
- No persistence.
- Manual IP address.
- Experimental local-network validation only.

