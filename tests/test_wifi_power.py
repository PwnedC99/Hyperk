"""Verify SDK units, reconnect handling, defaults, and build-time validation.

Run with: python3 tests/test_wifi_power.py
Uses a host C++ compiler and small SDK test doubles; no device is required.
"""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WifiPowerTests(unittest.TestCase):
    def test_sdk_contract_and_build_flags(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "A host C++ compiler is required")
        with tempfile.TemporaryDirectory() as directory:
            folder = pathlib.Path(directory)
            (folder / "Arduino.h").write_text("""#pragma once
#include <cstdint>
struct SerialStub { void print(const char*) {} void println(const char*) {} };
inline SerialStub Serial;
""")
            (folder / "WiFi.h").write_text("""#pragma once
using WiFiEvent_t = int;
enum { ARDUINO_EVENT_WIFI_STA_START, ARDUINO_EVENT_WIFI_AP_START,
       ARDUINO_EVENT_WIFI_STA_CONNECTED, OTHER_EVENT };
struct WifiStub {
    void (*callback)(WiFiEvent_t) = nullptr;
    void onEvent(void (*fn)(WiFiEvent_t)) { callback = fn; }
};
inline WifiStub WiFi;
""")
            (folder / "esp_wifi.h").write_text("""#pragma once
#include <cstdint>
inline int calls = 0, lastPower = 0, sleepCalls = 0, lastSleep = -1;
constexpr int WIFI_PS_NONE = 0, WIFI_PS_MIN_MODEM = 1;
inline int esp_wifi_set_ps(int mode) { ++sleepCalls; lastSleep = mode; return 0; }
constexpr int ESP_OK = 0;
inline int esp_wifi_set_max_tx_power(int8_t power) {
    ++calls; lastPower = power; return ESP_OK;
}
inline const char* esp_err_to_name(int) { return "error"; }
""")
            (folder / "test.cpp").write_text("""#include <cassert>
#include <WiFi.h>
#include <esp_wifi.h>
#include "wifi_power.h"
int main() {
    WifiPower::init();
    WifiPower::apply();
#ifdef WIFI_TX_POWER_DBM
    assert(calls == 1 && lastPower == int(WIFI_TX_POWER_DBM * 4));
    assert(WiFi.callback);
    WiFi.callback(ARDUINO_EVENT_WIFI_STA_START);
    WiFi.callback(ARDUINO_EVENT_WIFI_AP_START);
    WiFi.callback(ARDUINO_EVENT_WIFI_STA_CONNECTED);
    WiFi.callback(OTHER_EVENT);
    assert(calls == 4);
#else
    assert(calls == 0);
#ifdef WIFI_LOW_LATENCY
    assert(sleepCalls == 1 && lastSleep == (WIFI_LOW_LATENCY ? WIFI_PS_NONE : WIFI_PS_MIN_MODEM));
    assert(WiFi.callback);
    WiFi.callback(ARDUINO_EVENT_WIFI_STA_CONNECTED);
    assert(sleepCalls == 2);
#endif
#ifndef WIFI_LOW_LATENCY
    assert(!WiFi.callback);
#endif
#endif
}
""")
            for value in [None, "2", "17.25", "17.5", "20", "0", "21", "17.1", "latency0", "latency1", "latency2"]:
                with self.subTest(dbm=value):
                    command = [compiler, "-std=c++17", "-DARDUINO_ARCH_ESP32",
                               "-I" + str(folder), "-I" + str(ROOT / "include"),
                               str(ROOT / "src/wifi_power.cpp"), str(folder / "test.cpp"),
                               "-o", str(folder / "test")]
                    if value and value.startswith("latency"):
                        command.append("-DWIFI_LOW_LATENCY=" + value[-1])
                    elif value is not None:
                        command.append("-DWIFI_TX_POWER_DBM=" + value)
                    result = subprocess.run(command, capture_output=True, text=True)
                    if value in ["0", "21", "17.1", "latency2"]:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("static assertion failed", result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        subprocess.run([str(folder / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
