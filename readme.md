# Hyperk

Hyperk is a minimalist, high-performance uni-platform WiFi/Ethernet LED driver for ESP8266, ESP32 (S2, S3, C2, C3, C5, C6), Raspberry Pi Pico W (RP2040, RP2350). Designed as a lightweight and streamlined component that avoids unnecessary complexity, it delivers low‑latency performance and integrates smoothly with platforms such as HyperHDR, while offering essential home‑automation capabilities through a clean, modern codebase.

## Installation

The firmware can be flashed directly from your browser:
**[hyperk.hyperhdr.org](https://hyperk.hyperhdr.org)**

> [!TIP]
> Once installed, you can also perform OTA updates directly through the local **Web GUI**.

---

## Supported Hardware

- **Espressif:** ESP8266, ESP32, ESP32-S2, ESP32-S3, ESP32-C2, ESP32-C3, ESP32-C5, ESP32-C6, WT32-ETH01
   - Initial support for custom boards: GLEDOPTO, DOMRAEM, Athom/IoTorero including LAN8720 chipset  
   
- **Raspberry Pi Pico W:** RP2040, RP2350

Includes support for multi-segment (board-dependent), power-relay control, and HyperSerial (USB serial port communication).

## ESP32-S3FH4R2 fork

Use the dedicated profile for the 4 MB ESP32-S3FH4R2 board:

```sh
python3 -m pip install -r requirements-build.txt
pio run -e esp32s3-fh4r2
```

The generic `esp32s3` profile keeps its original board configuration. The custom
profile links the official `esp32s3` backend archive without modifying it.
`ccache` is optional. The LED library and build tools have pinned versions.

### ESP32-S3 USB / HyperSerial fix

The FH4R2 profile enables hardware USB CDC and bridges the pinned backend 0.0.5
UART0 calls to USB Serial/JTAG without modifying its parser or archive.
See [USB_SERIAL_FIX.md](USB_SERIAL_FIX.md) for validation results, limitations,
and OTA/application-only USB installation that preserves settings.

### Configuration storage

The FH4R2 profile writes configuration changes to a temporary file, validates
its JSON, and commits it by rename before reporting success. Failed saves return
HTTP 503 and do not schedule a reboot or apply the new LED configuration.
Invalid existing configurations are retained instead of triggering a filesystem
format. Only a completely erased filesystem partition is initialized automatically.
The settings forms and board diagnostics show storage failures explicitly.
See [CONFIG_STORAGE_FIX.md](CONFIG_STORAGE_FIX.md) for findings, validation,
limitations, and application-only installation instructions.

### GPIO1 peripheral control

Open **Settings → LED Hardware → Peripherie**, or open `/board.html` on the device.
The switch uses the same styling as the other LED hardware settings and switches
GPIO1 between LOW (off) and HIGH (on). Changes are saved immediately; the last selected state
is stored in NVS and restored after restart or loss of power. A fresh installation
starts with the peripheral output off. Repeated requests for the same state do
not rewrite flash. If saving fails, the output remains in its previous state.

GPIO1 is reserved for the peripheral output in this profile. It is excluded from
LED data/clock selectors, and the settings endpoint rejects GPIO1 as an LED or
relay pin. GPIO37 and GPIO38 are available as LED data and clock pins.

The board page also shows connection status, RSSI, the requested transmit-power
ceiling, the ceiling reported by the WiFi driver, disconnection reasons, and the
build ID. The driver-reported ceiling is not a measurement of radiated power.

### Local OTA firmware upload

Open **Settings → Firmware Update (OTA) → Lokale Firmware installieren**, select
the `OTA_Hyperk_...esp32s3-fh4r2_....bin` from your build, and click
**Firmware hochladen**. Confirm the selected file and keep power connected until
the device reports success and restarts. The page reloads after the restart.
The upload replaces the application; the existing partition table and settings
storage are preserved. This requires a compatible existing partition layout.

The file is checked for the ESP32-S3 chip ID, application descriptor, and the
maximum OTA slot size before uploading. Factory images are rejected. Upload
progress, device confirmation, and errors appear in the existing OTA section.
The original **Stable / Testing** channels remain available and fetch official
upstream firmware; use the local upload to install this custom board build.

The original 0.0.5 interface has no local file picker. To install the first build
with this extension, use the existing `/ota` endpoint from PowerShell (replace
the address and file path):

```powershell
$esp = "http://192.168.178.50"
$firmware = Get-Item "C:\Path\YOUR_OTA_FILE.bin"
curl.exe --fail-with-body --show-error `
  -H "hyperk-ota-firmware-size: $($firmware.Length)" `
  -H "hyperk-ota-firmware-name: OTA_Hyperk_local_esp32s3.bin" `
  -F "update=@$($firmware.FullName)" `
  "$esp/ota"
```

The firmware-name header matches the original ESP32-S3 backend's name check;
the selected file is uploaded unchanged. After the update, hard-refresh the
settings page once (Ctrl+F5), or open it in a private browser window, to replace
cached original scripts. Subsequent local updates can use the new file picker.

### WiFi options

Uncomment the desired build flags in `[env:modern-esp]` in `platformio.ini`.
These settings apply to all WiFi paths in the compiled ESP32 firmware:

```ini
    -DWIFI_TX_POWER_DBM=17.0
    -DWIFI_LOW_LATENCY=1
    -DWIFI_CONNECT_TIMEOUT_MS=12000
    -DWIFI_RETRY_INTERVAL_MS=15000
    -DWIFI_AP_FALLBACK_MS=30000
```

Transmit-power values must be 2..20 dBm in 0.25 dBm steps. Without the flag, the SDK
chooses its default. Actual limits can be rounded down or limited further by the
PHY and network/country configuration. `WIFI_LOW_LATENCY=1` disables modem sleep;
`0` enables minimum modem sleep. Without the flag, the SDK default is retained.
Disabling sleep trades increased power consumption for lower receive latency.
See the [Espressif WiFi documentation](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/api-guides/wifi.html#esp32-s3-wi-fi-power-saving-mode).

The custom profile retries stored credentials without periodic reboots. Initial
connection wait defaults to 12 seconds. Following a connection loss it retries
immediately, then every 15 seconds; after 30 seconds offline it starts the setup
access point. The initial startup fallback still starts the AP after the initial
connection timeout. Retries pause while a client is using the setup AP. On
recovery, the AP closes and mDNS/UDP listeners restart. No stored credentials
means setup mode remains active until WiFi is configured.

### Firmware identity and backend upgrades

`release/` contains factory and OTA images named with the profile and build ID.
A JSON manifest records the Git revision, dirty state, firmware source hash,
build flags, backend checksum, and SHA-256 of each output image. The ID describes
build inputs; byte-for-byte reproducibility across different hosts is not claimed.

Backend downloads are verified against `resources/backend_checksums.json`, written
to temporary files, and renamed only after successful verification. Existing
cached archives are checked on every build. An upgrade requires reviewing and
adding the official release checksums before changing `version`.

The UI extensions target backend 0.0.5 and load its original browser scripts at
runtime. After first flashing this fork, hard-refresh the settings page once to
clear previously cached scripts. Custom board and OTA scripts are served without caching.

### Tests

A host C++ compiler, Python 3.9+, and Node.js 22+ are required:

```sh
npm ci --ignore-scripts
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/check_backend_ui.py --output /tmp/hyperk-ui
HYPERK_BACKEND_FIXTURES=/tmp/hyperk-ui npm test
```

The backend UI check verifies the pinned binary archive and extracts only browser
assets for DOM tests. GitHub Actions runs these checks before building only `esp32s3-fh4r2`, with
defaults and with TX/latency options enabled. Other device profiles are available
for manual local builds and are not built by the workflow.

Hardware checks still required: toggle the actual GPIO1 load; power-cycle with
both saved states; interrupt/restore the router; and verify LED streaming and the
native backend pages after leaving setup mode. No device is flashed automatically.
For local OTA, also verify an actual upload, successful reboot, and retained WiFi,
LED settings, and peripheral state on the device.

## Supported LED Types

- **NeoPixel RGB:** WS2812b and compatible.
- **NeoPixel RGBW:** SK6812 (includes white channel calibration known from HyperSerial).
- **DotStar SPI:** APA102 and high-speed clocked LEDs.

## Manual

👉 [https://wiki.hyperhdr.eu/Hyperk](https://wiki.hyperhdr.eu/Hyperk)

## Integration

- **HyperHDR WiFi:** Dedicated Hyperk driver. Also works via its native `DDP`, `udpraw`, and `WLED` drivers.
- **HyperHDR Serial Port:** HyperHDR Adalight USB serial communication variant (AWA protocol).
- **Home Assistant:** Automatic discovery with support for power on/off, color, and brightness control.

|      HyperHDR      |   Home Assistant   |
|--------------------|--------------------|
| [![1](https://github.com/user-attachments/assets/ab252845-50da-4985-96be-d1da7bfd522d)](https://github.com/user-attachments/assets/ab252845-50da-4985-96be-d1da7bfd522d) | [![2a](https://github.com/user-attachments/assets/b3097b11-249a-4a66-9cff-bcdd70f28e87)](https://github.com/user-attachments/assets/b3097b11-249a-4a66-9cff-bcdd70f28e87) |


## Network Services

| Service | Port | Protocol / Description |
| :--- | :--- | :--- |
| Web GUI | 80 | Device configuration |
| UDP DDP | 4048 | DDP listener |
| UDP RealTime | 21324 | Real-time stream listener |
| UDP Raw RGB | 5568 | Raw color stream listener |
  
<small>LEDs turn off automatically 6.5s after stream loss.</small>

---
*Developed for performance. Optimized for HyperHDR. [Privacy & Technical Note](https://awawa-dev.github.io/hyperk/privacy.html)*
