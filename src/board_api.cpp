#ifdef HYPERK_BOARD_UI
#include <Arduino.h>
#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <atomic>
#include "network_recovery.h"
#include "board_pin_policy.h"
#include "board_api.h"
#include "build_info.h"
#include "peripheral.h"

namespace {
    std::atomic<uint32_t> disconnects{0};
    std::atomic<uint32_t> lastDisconnectMs{0};
    std::atomic<unsigned> lastDisconnectReason{0};
    const char* reasonName(unsigned reason) {
        switch (reason) {
            case 0: return "Noch kein Abbruch";
            case WIFI_REASON_NO_AP_FOUND: return "Access Point nicht gefunden";
            case WIFI_REASON_AUTH_FAIL: return "Authentifizierung fehlgeschlagen";
            case WIFI_REASON_HANDSHAKE_TIMEOUT: return "Anmeldung: Zeitüberschreitung";
            case WIFI_REASON_BEACON_TIMEOUT: return "Access Point antwortet nicht";
            case WIFI_REASON_ASSOC_LEAVE: return "Verbindung getrennt";
            default: return "Anderer Grund";
        }
    }
    void sendState(AsyncWebServerRequest* request) {
        JsonDocument doc;
        doc["peripheral"]["gpio"] = PERIPHERAL_ENABLE_GPIO;
        doc["peripheral"]["enabled"] = Peripheral::enabled();
        doc["peripheral"]["storage_ready"] = Peripheral::storageReady();
        const bool connected = WiFi.status() == WL_CONNECTED;
        doc["wifi"]["connected"] = connected;
        doc["wifi"]["ap_active"] = (WiFi.getMode() & WIFI_AP) != 0;
        doc["wifi"]["ip"] = connected ? WiFi.localIP().toString() : WiFi.softAPIP().toString();
        doc["wifi"]["channel"] = WiFi.channel();
        if (connected) doc["wifi"]["rssi_dbm"] = WiFi.RSSI();
        else doc["wifi"]["rssi_dbm"] = nullptr;
        #ifdef WIFI_TX_POWER_DBM
            doc["wifi"]["configured_tx_dbm"] = double(WIFI_TX_POWER_DBM);
        #else
            doc["wifi"]["configured_tx_dbm"] = nullptr;
        #endif
        int8_t power = 0;
        if (esp_wifi_get_max_tx_power(&power) == ESP_OK) doc["wifi"]["driver_tx_limit_dbm"] = power / 4.0;
        else doc["wifi"]["driver_tx_limit_dbm"] = nullptr;
        wifi_ps_type_t sleep = WIFI_PS_MIN_MODEM;
        if (esp_wifi_get_ps(&sleep) == ESP_OK) doc["wifi"]["low_latency"] = sleep == WIFI_PS_NONE;
        else doc["wifi"]["low_latency"] = nullptr;
        doc["wifi"]["disconnect_count"] = disconnects.load();
        doc["wifi"]["last_disconnect_reason"] = lastDisconnectReason.load();
        doc["wifi"]["last_disconnect_text"] = reasonName(lastDisconnectReason.load());
        doc["wifi"]["last_disconnect_ms"] = lastDisconnectMs.load();
        doc["wifi"]["connect_timeout_ms"] = WIFI_CONNECT_TIMEOUT_MS;
        doc["wifi"]["retry_interval_ms"] = WIFI_RETRY_INTERVAL_MS;
        doc["wifi"]["ap_fallback_ms"] = WIFI_AP_FALLBACK_MS;
        doc["uptime_ms"] = millis();
        doc["reset_reason"] = int(esp_reset_reason());
        #ifdef HYPERK_BUILD_ID
            doc["build_id"] = HYPERK_BUILD_ID;
        #else
            doc["build_id"] = PIO_ENV_NAME;
        #endif
        String body;
        serializeJson(doc, body);
        auto* response = request->beginResponse(200, "application/json", body);
        response->addHeader("Cache-Control", "no-store");
        request->send(response);
    }


}

void BoardApi::init() {
    Peripheral::init();
    WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
        if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
            lastDisconnectReason.store(info.wifi_sta_disconnected.reason);
            lastDisconnectMs.store(millis());
            disconnects.fetch_add(1);
        }
    });
}

void BoardApi::registerRoutes(AsyncWebServer& server) {
    server.on("/board", HTTP_GET, [](AsyncWebServerRequest* request) { request->redirect("/board.html"); });
    server.on("/api/board", HTTP_GET, sendState);
    server.on("/api/peripheral", HTTP_POST, [](AsyncWebServerRequest* request) {
        if (!request->hasParam("enabled", true)) {
            request->send(400, "application/json", "{\"error\":\"enabled must be 0 or 1\"}");
            return;
        }
        const String value = request->getParam("enabled", true)->value();
        if (value != "0" && value != "1") {
            request->send(400, "application/json", "{\"error\":\"enabled must be 0 or 1\"}");
            return;
        }
        if (!Peripheral::setEnabled(value == "1")) {
            request->send(503, "application/json", "{\"error\":\"Peripheral state could not be saved\"}");
            return;
        }
        sendState(request);
    });
    server.addMiddleware([](AsyncWebServerRequest* request, ArMiddlewareNext next) {
        if (request->method() == HTTP_POST && request->url() == "/save_config") {
            const bool badSegments = request->hasParam("segments", true) &&
                BoardPinPolicy::invalidSegments(request->getParam("segments", true)->value().c_str(), PERIPHERAL_ENABLE_GPIO);
            const bool badRelay = request->hasParam("relay-gpio", true) &&
                request->getParam("relay-gpio", true)->value().toInt() == PERIPHERAL_ENABLE_GPIO;
            if (badSegments || badRelay) {
                request->send(409, "application/json", "{\"error\":\"GPIO1 is reserved for peripherals\"}");
                return;
            }
        }
        next();
    });
}
#endif
