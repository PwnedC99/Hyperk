#pragma once
#include <cstdint>

namespace ConfigDiagnostics {
#ifdef HYPERK_CONFIG_DIAGNOSTICS
    void begin();
    void event(const char* phase, uint32_t value = 0);
    void poll();
#else
    inline void begin() {}
    inline void event(const char*, uint32_t = 0) {}
    inline void poll() {}
#endif
}
