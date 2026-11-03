#include "peripheral.h"

#ifdef PERIPHERAL_ENABLE_GPIO
#include <Preferences.h>
#include <driver/gpio.h>
#include <atomic>

static_assert(GPIO_IS_VALID_OUTPUT_GPIO(PERIPHERAL_ENABLE_GPIO), "Peripheral pin must be an output GPIO");
namespace {
    Preferences preferences;
    std::atomic<bool> active{false};
    bool ready = false;
    constexpr auto pin = static_cast<gpio_num_t>(PERIPHERAL_ENABLE_GPIO);
}

void Peripheral::init() {
    // Set the output latch before enabling the output driver.
    gpio_set_level(pin, 0);
    gpio_set_direction(pin, GPIO_MODE_OUTPUT);
    ready = preferences.begin("hyperk-board", false);
    const bool saved = ready && preferences.getBool("peripheral", false);
    gpio_set_level(pin, saved ? 1 : 0);
    active.store(saved);
}

bool Peripheral::enabled() { return active.load(); }
bool Peripheral::storageReady() { return ready; }
bool Peripheral::setEnabled(bool value) {
    if (value == active.load()) return true;
    // Do not claim persistence or change the output if the NVS write fails.
    if (!ready || preferences.putBool("peripheral", value) != 1) return false;
    if (gpio_set_level(pin, value ? 1 : 0) != ESP_OK) {
        preferences.putBool("peripheral", active.load());
        return false;
    }
    active.store(value);
    return true;
}
#else
void Peripheral::init() {}
bool Peripheral::enabled() { return false; }
bool Peripheral::storageReady() { return false; }
bool Peripheral::setEnabled(bool) { return false; }
#endif
