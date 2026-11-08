#ifdef HYPERK_USB_SERIAL_BRIDGE
#include <Arduino.h>

#if !defined(CONFIG_IDF_TARGET_ESP32S3) || ARDUINO_USB_CDC_ON_BOOT != 1 || ARDUINO_USB_MODE != 1
#error "The USB serial bridge requires ESP32-S3 hardware CDC on boot"
#endif

// Backend 0.0.5 binds HyperSerial to UART0 before our build flags are applied.
extern "C" {
void realSerialBegin(HardwareSerial*, unsigned long, uint32_t, int8_t, int8_t, bool, unsigned long, uint8_t)
    asm("__real__ZN14HardwareSerial5beginEmmaabmh");
size_t realSerialRxBuffer(HardwareSerial*, size_t) asm("__real__ZN14HardwareSerial15setRxBufferSizeEj");
int realSerialAvailable(HardwareSerial*) asm("__real__ZN14HardwareSerial9availableEv");
int realSerialRead(HardwareSerial*) asm("__real__ZN14HardwareSerial4readEv");
size_t realSerialReadBytes(HardwareSerial*, uint8_t*, size_t) asm("__real__ZN14HardwareSerial9readBytesEPhj");
void realSerialFlush(HardwareSerial*) asm("__real__ZN14HardwareSerial5flushEv");
size_t realPrintText(Print*, const char*) asm("__real__ZN5Print5printEPKc");
size_t realPrintInt(Print*, int, int) asm("__real__ZN5Print5printEii");
size_t realPrintUint(Print*, unsigned int, int) asm("__real__ZN5Print5printEji");
size_t realPrintLine(Print*, const char*) asm("__real__ZN5Print7printlnEPKc");

void usbSerialBegin(HardwareSerial*, unsigned long, uint32_t, int8_t, int8_t, bool, unsigned long, uint8_t)
    asm("__wrap__ZN14HardwareSerial5beginEmmaabmh");
size_t usbSerialRxBuffer(HardwareSerial*, size_t) asm("__wrap__ZN14HardwareSerial15setRxBufferSizeEj");
int usbSerialAvailable(HardwareSerial*) asm("__wrap__ZN14HardwareSerial9availableEv");
int usbSerialRead(HardwareSerial*) asm("__wrap__ZN14HardwareSerial4readEv");
size_t usbSerialReadBytes(HardwareSerial*, uint8_t*, size_t) asm("__wrap__ZN14HardwareSerial9readBytesEPhj");
void usbSerialFlush(HardwareSerial*) asm("__wrap__ZN14HardwareSerial5flushEv");
size_t usbPrintText(Print*, const char*) asm("__wrap__ZN5Print5printEPKc");
size_t usbPrintInt(Print*, int, int) asm("__wrap__ZN5Print5printEii");
size_t usbPrintUint(Print*, unsigned int, int) asm("__wrap__ZN5Print5printEji");
size_t usbPrintLine(Print*, const char*) asm("__wrap__ZN5Print7printlnEPKc");
}

namespace {
    Print* printTarget(Print* port) {
        return port == static_cast<Print*>(&Serial0) ? static_cast<Print*>(&HWCDCSerial) : port;
    }
}

void usbSerialBegin(HardwareSerial* port, unsigned long baud, uint32_t config,
                    int8_t rx, int8_t tx, bool invert, unsigned long timeout, uint8_t threshold) {
    if (port == &Serial0) HWCDCSerial.begin(baud);
    else realSerialBegin(port, baud, config, rx, tx, invert, timeout, threshold);
}

size_t usbSerialRxBuffer(HardwareSerial* port, size_t size) {
    return port == &Serial0 ? HWCDCSerial.setRxBufferSize(size) : realSerialRxBuffer(port, size);
}

int usbSerialAvailable(HardwareSerial* port) {
    return port == &Serial0 ? HWCDCSerial.available() : realSerialAvailable(port);
}

int usbSerialRead(HardwareSerial* port) {
    return port == &Serial0 ? HWCDCSerial.read() : realSerialRead(port);
}

size_t usbSerialReadBytes(HardwareSerial* port, uint8_t* buffer, size_t size) {
    if (port != &Serial0) return realSerialReadBytes(port, buffer, size);
    HWCDCSerial.setTimeout(port->getTimeout());
    return HWCDCSerial.readBytes(buffer, size);
}

void usbSerialFlush(HardwareSerial* port) {
    if (port == &Serial0) HWCDCSerial.flush();
    else realSerialFlush(port);
}

size_t usbPrintText(Print* port, const char* text) {
    return realPrintText(printTarget(port), text);
}

size_t usbPrintInt(Print* port, int value, int base) {
    return realPrintInt(printTarget(port), value, base);
}

size_t usbPrintUint(Print* port, unsigned int value, int base) {
    return realPrintUint(printTarget(port), value, base);
}

size_t usbPrintLine(Print* port, const char* text) {
    return realPrintLine(printTarget(port), text);
}
#endif
