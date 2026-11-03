#include <Arduino.h>
#include "wifi_power.h"

#if defined(WIFI_TX_POWER_DBM) || defined(WIFI_LOW_LATENCY)
    #if !defined(ARDUINO_ARCH_ESP32)
        #error "WiFi TX/latency build options require an ESP32 target"
    #endif
    #include <WiFi.h>
    #include <esp_wifi.h>

    #ifdef WIFI_TX_POWER_DBM
    namespace {
        constexpr double txPowerDbm = WIFI_TX_POWER_DBM;
        static_assert(txPowerDbm >= 2.0 && txPowerDbm <= 20.0,
                      "WIFI_TX_POWER_DBM must be between 2 and 20 dBm");
        static_assert(txPowerDbm * 4 == static_cast<int>(txPowerDbm * 4),
                      "WIFI_TX_POWER_DBM must use 0.25 dBm steps");
    }
    #endif
    #ifdef WIFI_LOW_LATENCY
        static_assert(WIFI_LOW_LATENCY == 0 || WIFI_LOW_LATENCY == 1, "WIFI_LOW_LATENCY must be 0 or 1");
    #endif
#endif

void WifiPower::apply() {
    #ifdef WIFI_TX_POWER_DBM
        // ESP-IDF expects quarter-dBm units and a running WiFi driver.
        const auto result = esp_wifi_set_max_tx_power(static_cast<int8_t>(txPowerDbm * 4));
        if (result != ESP_OK) {
            Serial.print("Failed to set WiFi TX power: ");
            Serial.println(esp_err_to_name(result));
        }
    #endif
    #ifdef WIFI_LOW_LATENCY
        const auto sleepResult = esp_wifi_set_ps(WIFI_LOW_LATENCY ? WIFI_PS_NONE : WIFI_PS_MIN_MODEM);
        if (sleepResult != ESP_OK) {
            Serial.print("Failed to set WiFi sleep mode: ");
            Serial.println(esp_err_to_name(sleepResult));
        }
    #endif
}

void WifiPower::init() {
    #if defined(WIFI_TX_POWER_DBM) || defined(WIFI_LOW_LATENCY)
        WiFi.onEvent([](WiFiEvent_t event) {
            // Reapply after driver restarts and association/country updates.
            if (event == ARDUINO_EVENT_WIFI_STA_START ||
                event == ARDUINO_EVENT_WIFI_AP_START ||
                event == ARDUINO_EVENT_WIFI_STA_CONNECTED) {
                apply();
            }
        });
    #endif
}
