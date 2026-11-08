#pragma once
#ifdef HYPERK_CONFIG_STORE
namespace ConfigStore {
    bool begin();
    bool mounted();
    bool configValid();
    bool lastSaveSucceeded();
    bool saveAttempted();
    const char* error();
    void beginRequest();
    bool requestFailed();
    void endRequest();
}
#endif
