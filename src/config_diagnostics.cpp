#ifdef HYPERK_CONFIG_DIAGNOSTICS
#include <Arduino.h>
#include <esp_heap_caps.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <cstring>
#include "build_info.h"
#include "config_diagnostics.h"

namespace {
    constexpr unsigned capacity = 64, lineSize = 192;
    char lines[capacity][lineSize];
    unsigned head = 0, tail = 0;
    portMUX_TYPE logMux = portMUX_INITIALIZER_UNLOCKED;
}

void ConfigDiagnostics::begin() {
    Serial.begin(115200);
    Serial.setTxTimeoutMs(10);
    event("[BOOT] Reset reason", esp_reset_reason());
    event("[BOOT] Diagnostic mode; HyperSerial disabled");
    event("[BOOT] Build " HYPERK_BUILD_ID);
}

void ConfigDiagnostics::event(const char* phase, uint32_t value) {
    char line[lineSize] = {};
    snprintf(line, sizeof(line), "%lu %s value=%lu heap=%lu largest=%u stack_free=%u\n",
        millis(), phase, static_cast<unsigned long>(value), ESP.getFreeHeap(),
        heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        uxTaskGetStackHighWaterMark(nullptr));
    portENTER_CRITICAL(&logMux);
    memcpy(lines[head], line, sizeof(line));
    head = (head + 1) % capacity;
    if (head == tail) tail = (tail + 1) % capacity;
    portEXIT_CRITICAL(&logMux);
}

void ConfigDiagnostics::poll() {
    if (!Serial) return;
    for (unsigned i = 0; i < 4; ++i) {
        char line[lineSize];
        portENTER_CRITICAL(&logMux);
        const bool available = tail != head;
        if (available) {
            memcpy(line, lines[tail], sizeof(line));
            tail = (tail + 1) % capacity;
        }
        portEXIT_CRITICAL(&logMux);
        if (!available) break;
        Serial.print(line);
    }
}
#endif
