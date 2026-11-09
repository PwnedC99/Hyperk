#ifdef HYPERK_CONFIG_STORE
#include <atomic>
#include <led_strip_rmt.h>
#include <led_strip_spi.h>
#include <driver/rmt_tx.h>
#include "config_store.h"
#include "config_diagnostics.h"

extern "C" {
    void realLedApply() asm("__real__ZN4Leds14applyLedConfigEv");
    void guardedLedApply() asm("__wrap__ZN4Leds14applyLedConfigEv");
    esp_err_t __real_led_strip_new_spi_device(const led_strip_config_t*, const led_strip_spi_config_t*, led_strip_handle_t*);
    esp_err_t __real_led_strip_new_rmt_device(const led_strip_config_t*, const led_strip_rmt_config_t*, led_strip_handle_t*);
    esp_err_t __real_rmt_new_sync_manager(const rmt_sync_manager_config_t*, rmt_sync_manager_handle_t*);
}
namespace {
    std::atomic<bool> failed{false};
    esp_err_t record(const char* phase, esp_err_t result) {
        if (result != ESP_OK) failed.store(true);
        ConfigDiagnostics::event(phase, result);
        return result;
    }
}
void guardedLedApply() {
    ConfigStore::runLocked([] {
        if (!ConfigStore::beginLedInit()) {
            ConfigDiagnostics::event("[BOOT] LED initialization skipped; recovery or storage unavailable");
            return;
        }
        failed.store(false);
        ConfigDiagnostics::event("[LED] Initialization started");
        realLedApply();
        ConfigStore::endLedInit(!failed.load());
        ConfigDiagnostics::event("[BOOT] LED initialization result", !failed.load());
    });
}
extern "C" esp_err_t __wrap_led_strip_new_spi_device(const led_strip_config_t* config,
    const led_strip_spi_config_t* spi, led_strip_handle_t* strip) {
    ConfigDiagnostics::event("[LED] SPI data GPIO", config ? config->strip_gpio_num : uint32_t(-1));
    return record("[LED] SPI create result", __real_led_strip_new_spi_device(config, spi, strip));
}
extern "C" esp_err_t __wrap_led_strip_new_rmt_device(const led_strip_config_t* config,
    const led_strip_rmt_config_t* rmt, led_strip_handle_t* strip) {
    ConfigDiagnostics::event("[LED] RMT data GPIO", config ? config->strip_gpio_num : uint32_t(-1));
    return record("[LED] RMT create result", __real_led_strip_new_rmt_device(config, rmt, strip));
}
extern "C" esp_err_t __wrap_rmt_new_sync_manager(const rmt_sync_manager_config_t* config,
    rmt_sync_manager_handle_t* manager) {
    return record("[LED] RMT sync create result", __real_rmt_new_sync_manager(config, manager));
}
#endif
