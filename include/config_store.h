#pragma once
#include <cstdint>
#ifdef HYPERK_CONFIG_STORE
namespace ConfigStore {
    bool begin();
    bool mounted();
    bool configValid();
    bool lastSaveSucceeded();
    bool saveAttempted();
    const char* error();
    uint32_t publicChecksum();
    bool syncFile(const char* path);
    bool beginLedInit();
    void endLedInit(bool succeeded);
    bool ledRecovery();
    void runLocked(void (*operation)());
    void beginRequest();
    bool requestFailed();
    void endRequest();
}
#endif
