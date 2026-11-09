#ifdef HYPERK_CONFIG_STORE
#include <fcntl.h>
#include <unistd.h>
#include <cstdio>
#include "config_store.h"

bool ConfigStore::syncFile(const char* path) {
    char fullPath[96];
    const int length = snprintf(fullPath, sizeof(fullPath), "/littlefs%s", path);
    if (length < 0 || size_t(length) >= sizeof(fullPath)) return false;
    const int descriptor = open(fullPath, O_RDONLY);
    if (descriptor < 0) return false;
    const bool synced = fsync(descriptor) == 0;
    const bool closed = close(descriptor) == 0;
    return synced && closed;
}
#endif
