"""Exercise the real GPIO controller with host NVS/GPIO test doubles."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class PeripheralTests(unittest.TestCase):
    def test_persistence_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            p = pathlib.Path(directory)
            (p / "driver").mkdir()
            (p / "Preferences.h").write_text("""#pragma once
#include <cstddef>
inline bool saved = false, storageFails = false;
inline int writes = 0;
struct Preferences {
    bool begin(const char*, bool) { return true; }
    bool getBool(const char*, bool) { return saved; }
    size_t putBool(const char*, bool value) {
        if (storageFails) return 0;
        saved = value; ++writes; return 1;
    }
};
""")
            (p / "driver/gpio.h").write_text("""#pragma once
#define GPIO_IS_VALID_OUTPUT_GPIO(pin) ((pin) >= 0 && (pin) < 49)
using gpio_num_t = int;
constexpr int GPIO_MODE_OUTPUT = 1, ESP_OK = 0;
inline int level = -1, direction = 0;
inline int gpio_set_level(int pin, int value) { level = value; return 0; }
inline int gpio_set_direction(int pin, int value) { direction = value; return 0; }
""")
            (p / "test.cpp").write_text("""#include <cassert>
#include <Preferences.h>
#include <driver/gpio.h>
#include "peripheral.h"
int main() {
    Peripheral::init();
    assert(!Peripheral::enabled() && level == 0 && direction == GPIO_MODE_OUTPUT);
    assert(Peripheral::storageReady() && writes == 0);
    assert(Peripheral::setEnabled(true));
    assert(Peripheral::enabled() && saved && level == 1 && writes == 1);
    assert(Peripheral::setEnabled(true) && writes == 1);
    Peripheral::init(); // Simulate a reboot while NVS retains the stored value.
    assert(Peripheral::enabled() && level == 1 && writes == 1);
    storageFails = true;
    assert(!Peripheral::setEnabled(false));
    assert(Peripheral::enabled() && level == 1 && saved);
    storageFails = false;
    assert(Peripheral::setEnabled(false));
    Peripheral::init();
    assert(!Peripheral::enabled() && level == 0 && !saved);
}
""")
            result = subprocess.run([shutil.which("c++"), "-std=c++17", "-DPERIPHERAL_ENABLE_GPIO=1",
                "-I"+str(p), "-I"+str(ROOT/"include"), str(ROOT/"src/peripheral.cpp"),
                str(p/"test.cpp"), "-o", str(p/"test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(p/"test")], check=True)

if __name__ == "__main__":
    unittest.main()
