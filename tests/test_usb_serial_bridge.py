"""Exercise native USB routing without replacing the backend frame parser."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UsbSerialBridgeTests(unittest.TestCase):
    def test_linker_wrappers_match_the_adapter(self):
        source = (ROOT / "src/usb_serial_bridge.cpp").read_text()
        wrappers = set(re.findall(r'asm\("__wrap_([^\"]+)"\)', source))
        originals = set(re.findall(r'asm\("__real_([^\"]+)"\)', source))
        config = (ROOT / "platformio.ini").read_text().split("[env:esp32s3-fh4r2]", 1)[1].split("[env:", 1)[0]
        flags = set(re.findall(r"-Wl,--wrap=(\S+)", config))
        self.assertEqual(wrappers, originals)
        self.assertEqual(len(wrappers), 10)
        self.assertTrue(wrappers.issubset(flags))
        self.assertIn("-DHYPERK_USB_SERIAL_BRIDGE", config)

    def test_usb_routing_and_uart_fallback(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "A host C++ compiler is required")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "Arduino.h").write_text(r'''#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>
struct Print {};
struct HardwareSerial : Print {
    unsigned long timeout = 1000;
    unsigned long getTimeout() { return timeout; }
};
struct HWCDC : Print {
    std::vector<uint8_t> input;
    size_t rxSize = 0, position = 0;
    unsigned long baud = 0, timeout = 0;
    int starts = 0, flushes = 0;
    void begin(unsigned long value) { baud = value; ++starts; }
    size_t setRxBufferSize(size_t size) { rxSize = size; return size; }
    void setTimeout(unsigned long value) { timeout = value; }
    int available() { return input.size() - position; }
    int read() { return available() ? input[position++] : -1; }
    size_t readBytes(uint8_t* buffer, size_t size) {
        size_t count = 0;
        while (count < size && available()) buffer[count++] = input[position++];
        return count;
    }
    void flush() { ++flushes; }
};
inline HardwareSerial Serial0;
inline HWCDC HWCDCSerial;
''')
            (folder / "test.cpp").write_text(r'''#include <cassert>
#include <cstring>
#include "usb_serial_bridge.cpp"
int fallback = 0;
Print* printed = nullptr;
int number = 0, radix = 0;
const char* message = nullptr;
void realSerialBegin(HardwareSerial*, unsigned long baud, uint32_t config, int8_t rx,
                     int8_t tx, bool invert, unsigned long timeout, uint8_t threshold) {
    assert(baud == 115200 && config == 42 && rx == 4 && tx == 5 && invert && timeout == 800 && threshold == 16);
    ++fallback;
}
size_t realSerialRxBuffer(HardwareSerial*, size_t size) { ++fallback; return size; }
int realSerialAvailable(HardwareSerial*) { ++fallback; return 7; }
int realSerialRead(HardwareSerial*) { ++fallback; return 13; }
size_t realSerialReadBytes(HardwareSerial*, uint8_t* buffer, size_t size) {
    ++fallback; memset(buffer, 0xee, size); return size;
}
void realSerialFlush(HardwareSerial*) { ++fallback; }
size_t realPrintText(Print* port, const char* text) { printed = port; message = text; return 11; }
size_t realPrintInt(Print* port, int value, int base) { printed = port; number = value; radix = base; return 12; }
size_t realPrintUint(Print* port, unsigned int value, int base) { printed = port; number = value; radix = base; return 13; }
size_t realPrintLine(Print* port, const char* text) { printed = port; message = text; return 14; }
int main() {
    assert(usbSerialRxBuffer(&Serial0, 2048) == 2048 && HWCDCSerial.rxSize == 2048);
    for (auto baud : {2000000UL, 921600UL}) {
        usbSerialBegin(&Serial0, baud, 0, -1, -1, false, 0, 0);
        assert(HWCDCSerial.baud == baud);
    }
    assert(HWCDCSerial.starts == 2 && fallback == 0);
    assert(usbSerialAvailable(&Serial0) == 0 && usbSerialRead(&Serial0) == -1);
    uint8_t buffer[1200] = {};
    assert(usbSerialReadBytes(&Serial0, buffer, 0) == 0);
    std::vector<uint8_t> frame(258 * 4 + 9);
    for (size_t i = 0; i < frame.size(); ++i) frame[i] = i % 251;
    HWCDCSerial.input.assign(frame.begin(), frame.begin() + 17);
    assert(usbSerialAvailable(&Serial0) == 17);
    assert(usbSerialRead(&Serial0) == frame[0]);
    Serial0.timeout = 150;
    assert(usbSerialReadBytes(&Serial0, buffer + 1, 16) == 16 && HWCDCSerial.timeout == 150);
    buffer[0] = frame[0];
    assert(usbSerialAvailable(&Serial0) == 0);
    HWCDCSerial.input.insert(HWCDCSerial.input.end(), frame.begin() + 17, frame.end());
    assert(usbSerialReadBytes(&Serial0, buffer + 17, frame.size() - 17) == frame.size() - 17);
    assert(memcmp(buffer, frame.data(), frame.size()) == 0);
    usbSerialFlush(&Serial0);
    assert(HWCDCSerial.flushes == 1 && fallback == 0);
    assert(usbPrintText(&Serial0, "Awa driver") == 11 && printed == &HWCDCSerial);
    assert(strcmp(message, "Awa driver") == 0);
    assert(usbPrintInt(&Serial0, -42, 10) == 12 && printed == &HWCDCSerial && number == -42 && radix == 10);
    assert(usbPrintUint(&Serial0, 42, 16) == 13 && printed == &HWCDCSerial && number == 42 && radix == 16);
    assert(usbPrintLine(&Serial0, "stats") == 14 && printed == &HWCDCSerial && strcmp(message, "stats") == 0);
    HardwareSerial uart1;
    usbSerialBegin(&uart1, 115200, 42, 4, 5, true, 800, 16);
    assert(usbSerialRxBuffer(&uart1, 512) == 512);
    assert(usbSerialAvailable(&uart1) == 7 && usbSerialRead(&uart1) == 13);
    assert(usbSerialReadBytes(&uart1, buffer, 3) == 3 && buffer[0] == 0xee);
    usbSerialFlush(&uart1);
    assert(fallback == 6 && HWCDCSerial.starts == 2 && HWCDCSerial.flushes == 1);
    Print file;
    for (Print* port : {static_cast<Print*>(&uart1), &file}) {
        usbPrintText(port, "other"); assert(printed == port);
        usbPrintInt(port, 1, 10); assert(printed == port);
        usbPrintUint(port, 1, 10); assert(printed == port);
        usbPrintLine(port, "other"); assert(printed == port);
    }
}
''')
            command = [compiler, "-std=c++17", "-DHYPERK_USB_SERIAL_BRIDGE",
                       "-DCONFIG_IDF_TARGET_ESP32S3=1", "-DARDUINO_USB_CDC_ON_BOOT=1",
                       "-DARDUINO_USB_MODE=1", "-I" + str(folder), "-I" + str(ROOT / "src"),
                       str(folder / "test.cpp"), "-o", str(folder / "test")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(folder / "test")], check=True)
            invalid = [flag for flag in command if flag != "-DARDUINO_USB_CDC_ON_BOOT=1"]
            result = subprocess.run(invalid, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires ESP32-S3 hardware CDC", result.stderr)


if __name__ == "__main__":
    unittest.main()
