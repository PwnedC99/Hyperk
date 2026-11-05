// Add routes through the public web-server API; keep the backend archive unchanged.
#ifdef HYPERK_S3_EXTRA_GPIOS
#include <Arduino.h>
#if !defined(CONFIG_IDF_TARGET_ESP32S3) || !defined(USE_ASYNC_WEBSERWER)
#error "HYPERK_S3_EXTRA_GPIOS requires ESP32-S3 and ESPAsyncWebServer"
#endif
#include <ESPAsyncWebServer.h>
#include <cstring>
#include "web_resource.h"
#include "board_api.h"

namespace {
    constexpr char extensionPath[] = "/hyperk_s3_gpio.js";
    void sendAsset(AsyncWebServerRequest* request, const char* path) {
        for (uint16_t i = 0; i < webResourcesCount_OSS; ++i) {
            const auto& resource = webResources_OSS[i];
            if (strcmp(resource.url, path) != 0) continue;
            auto* response = request->beginResponse(200, resource.mime,
                reinterpret_cast<const uint8_t*>(resource.data), resource.len);
            response->addHeader("Content-Encoding", "gzip");
            response->addHeader("Cache-Control", "no-store");
            request->send(response);
            return;
        }
        request->send(500, "text/plain", "Board UI asset missing");
    }
}
extern "C" void __real__ZN14AsyncWebServer5beginEv(AsyncWebServer* server);
extern "C" void __wrap__ZN14AsyncWebServer5beginEv(AsyncWebServer* server) {
    server->rewrite("/settings_led_hardware.js", extensionPath)
        .setFilter([](AsyncWebServerRequest* request) {
            return request->method() == HTTP_GET && !request->hasParam("hyperk_original");
        });
    server->on(extensionPath, HTTP_GET, [](AsyncWebServerRequest* request) {
        sendAsset(request, "/s3_gpio_extension.js");
    });
    server->rewrite("/settings_ota.js", "/hyperk_ota.js")
        .setFilter([](AsyncWebServerRequest* request) {
            return request->method() == HTTP_GET && !request->hasParam("hyperk_original");
        });
    server->on("/hyperk_ota.js", HTTP_GET, [](AsyncWebServerRequest* request) {
        sendAsset(request, "/ota_extension.js");
    });
    server->rewrite("/board_controls.js", "/hyperk_board_controls.js");
    server->on("/hyperk_board_controls.js", HTTP_GET, [](AsyncWebServerRequest* request) {
        sendAsset(request, "/board_controls.js");
    });
    server->rewrite("/board.html", "/hyperk_board_page");
    server->on("/hyperk_board_page", HTTP_GET, [](AsyncWebServerRequest* request) {
        sendAsset(request, "/board.html");
    });
    #ifdef HYPERK_BOARD_UI
        BoardApi::registerRoutes(*server);
    #endif
    __real__ZN14AsyncWebServer5beginEv(server);
}
#endif
