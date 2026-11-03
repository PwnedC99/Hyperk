#pragma once
#include <cstdint>

#ifndef WIFI_CONNECT_TIMEOUT_MS
#define WIFI_CONNECT_TIMEOUT_MS 12000
#endif
#ifndef WIFI_RETRY_INTERVAL_MS
#define WIFI_RETRY_INTERVAL_MS 15000
#endif
#ifndef WIFI_AP_FALLBACK_MS
#define WIFI_AP_FALLBACK_MS 30000
#endif
static_assert(WIFI_CONNECT_TIMEOUT_MS >= 1000 && WIFI_CONNECT_TIMEOUT_MS <= 120000, "WiFi connect timeout: 1000..120000 ms");
static_assert(WIFI_RETRY_INTERVAL_MS >= 1000 && WIFI_RETRY_INTERVAL_MS <= 600000, "WiFi retry interval: 1000..600000 ms");
static_assert(WIFI_AP_FALLBACK_MS >= 1000 && WIFI_AP_FALLBACK_MS <= 600000, "WiFi AP fallback: 1000..600000 ms");

namespace NetworkRecovery {
    enum class Action { None, Retry, StartAP, CloseAP };
    // Pure timing policy, independent of the SDK and hardware.
    class Policy {
        bool configured_ = false;
        bool connected_ = false;
        uint32_t offlineSince_ = 0;
        uint32_t lastAttempt_ = 0;
    public:
        void begin(bool configured, bool connected, uint32_t now) {
            configured_ = configured; connected_ = connected;
            offlineSince_ = lastAttempt_ = now;
        }
        Action poll(uint32_t now, bool connected, bool accessPoint, bool apHasClients) {
            if (!configured_) return Action::None;
            if (connected) {
                connected_ = true;
                offlineSince_ = lastAttempt_ = now;
                return accessPoint ? Action::CloseAP : Action::None;
            }
            if (connected_) {
                connected_ = false;
                offlineSince_ = now;
                lastAttempt_ = now - WIFI_RETRY_INTERVAL_MS;
            }
            if (!accessPoint && static_cast<uint32_t>(now - offlineSince_) >= WIFI_AP_FALLBACK_MS)
                return Action::StartAP;
            if (!apHasClients && static_cast<uint32_t>(now - lastAttempt_) >= WIFI_RETRY_INTERVAL_MS) {
                lastAttempt_ = now;
                return Action::Retry;
            }
            return Action::None;
        }
    };
}
