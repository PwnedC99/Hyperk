#ifdef HYPERK_CONFIG_STORE
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <esp_partition.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/semphr.h>
#include <atomic>
#include <cstring>
#include "config_store.h"

class AppConfig;
namespace Config { bool loadConfig(); }
bool realConfigSave(const AppConfig&) asm("__real__ZN6Config10saveConfigERK9AppConfig");
bool protectedConfigSave(const AppConfig&) asm("__wrap__ZN6Config10saveConfigERK9AppConfig");
bool realStoreSave(const AppConfig&) asm("__real__ZN7Storage10saveConfigERK9AppConfig");
bool realStoreLoad(AppConfig&) asm("__real__ZN7Storage10loadConfigER9AppConfig");
fs::File realStoreOpen(fs::FS*, const char*, const char*, bool) asm("__real__ZN2fs2FS4openEPKcS2_b");
bool realStoreFormat(fs::LittleFSFS*) asm("__real__ZN2fs10LittleFSFS6formatEv");
void realStoreReboot(unsigned long) asm("__real__ZN7Manager14scheduleRebootEm");
void realStoreApply() asm("__real__ZN7Manager19scheduleApplyConfigEv");
bool protectedStoreSave(const AppConfig&) asm("__wrap__ZN7Storage10saveConfigERK9AppConfig");
bool protectedStoreLoad(AppConfig&) asm("__wrap__ZN7Storage10loadConfigER9AppConfig");
fs::File protectedStoreOpen(fs::FS*, const char*, const char*, bool) asm("__wrap__ZN2fs2FS4openEPKcS2_b");
bool protectedStoreFormat(fs::LittleFSFS*) asm("__wrap__ZN2fs10LittleFSFS6formatEv");
void protectedStoreReboot(unsigned long) asm("__wrap__ZN7Manager14scheduleRebootEm");
void protectedStoreApply() asm("__wrap__ZN7Manager19scheduleApplyConfigEv");

namespace {
    constexpr char configPath[] = "/config.json";
    constexpr char pendingPath[] = "/config.pending.json";
    std::atomic<bool> filesystemMounted{false}, validConfig{false}, saveSucceeded{false}, attemptedSave{false};
    std::atomic<const char*> lastError{"not_checked"};
    std::atomic<TaskHandle_t> writingTask{nullptr}, loadingTask{nullptr}, requestTask{nullptr};
    bool failedRequest = false;
    StaticSemaphore_t mutexStorage;
    SemaphoreHandle_t mutex() {
        static SemaphoreHandle_t handle = xSemaphoreCreateRecursiveMutexStatic(&mutexStorage);
        return handle;
    }
    struct Lock {
        Lock() { xSemaphoreTakeRecursive(mutex(), portMAX_DELAY); }
        ~Lock() { xSemaphoreGiveRecursive(mutex()); }
    };
    bool failSave(const char* reason) {
        attemptedSave.store(true);
        saveSucceeded.store(false);
        lastError.store(reason);
        if (requestTask.load() == xTaskGetCurrentTaskHandle()) failedRequest = true;
        return false;
    }
    bool validFile(const char* path) {
        auto file = LittleFS.open(path, "r");
        if (!file || file.size() == 0 || file.size() > 16384) return false;
        JsonDocument doc;
        const bool parsed = !deserializeJson(doc, file);
        bool trailingData = false;
        while (file.available()) {
            const int value = file.read();
            if (value != ' ' && value != '\n' && value != '\r' && value != '\t') trailingData = true;
        }
        file.close();
        return parsed && !trailingData && doc.is<JsonObject>() &&
            doc["wifi"].is<JsonObject>() && doc["segments"].is<JsonArray>() &&
            doc["numLeds"].is<unsigned int>();
    }
    bool erasedPartition() {
        const auto* partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA,
            ESP_PARTITION_SUBTYPE_DATA_SPIFFS, "spiffs");
        if (!partition) return false;
        uint8_t buffer[256];
        for (size_t offset = 0; offset < partition->size; offset += sizeof(buffer)) {
            const size_t length = partition->size - offset < sizeof(buffer) ? partition->size - offset : sizeof(buffer);
            if (esp_partition_read(partition, offset, buffer, length) != ESP_OK) return false;
            for (size_t i = 0; i < length; ++i) if (buffer[i] != 0xff) return false;
        }
        return true;
    }
    bool blockScheduledChange() {
        return requestTask.load() == xTaskGetCurrentTaskHandle() && failedRequest;
    }
}

bool ConfigStore::begin() {
    Lock lock;
    bool ready = LittleFS.begin(false);
    // Only initialize completely erased storage; retain damaged filesystems for recovery.
    if (!ready && erasedPartition()) ready = LittleFS.format() && LittleFS.begin(false);
    filesystemMounted.store(ready);
    lastError.store(ready ? "none" : "filesystem_mount_failed");
    return ready;
}
bool ConfigStore::mounted() { return filesystemMounted.load(); }
bool ConfigStore::configValid() { return validConfig.load(); }
bool ConfigStore::lastSaveSucceeded() { return saveSucceeded.load(); }
bool ConfigStore::saveAttempted() { return attemptedSave.load(); }
const char* ConfigStore::error() { return lastError.load(); }
void ConfigStore::beginRequest() {
    xSemaphoreTakeRecursive(mutex(), portMAX_DELAY);
    failedRequest = false;
    requestTask.store(xTaskGetCurrentTaskHandle());
}
bool ConfigStore::requestFailed() { return failedRequest; }
void ConfigStore::endRequest() {
    requestTask.store(nullptr);
    xSemaphoreGiveRecursive(mutex());
}

bool protectedConfigSave(const AppConfig& config) {
    Lock lock;
    const bool saved = realConfigSave(config);
    if (!saved && filesystemMounted.load() && validFile(configPath)) {
        const char* reason = lastError.load();
        const bool restored = Config::loadConfig();
        lastError.store(restored ? reason : "save_failed_and_reload_failed");
    }
    return saved;
}

bool protectedStoreSave(const AppConfig& config) {
    Lock lock;
    if (!filesystemMounted.load()) return failSave("filesystem_not_mounted");
    if (loadingTask.load() == xTaskGetCurrentTaskHandle()) return failSave("backend_load_failed");
    if (LittleFS.exists(pendingPath) && !LittleFS.remove(pendingPath)) return failSave("pending_cleanup_failed");
    attemptedSave.store(true);
    writingTask.store(xTaskGetCurrentTaskHandle());
    const bool written = realStoreSave(config);
    writingTask.store(nullptr);
    if (!written) return failSave("backend_write_failed");
    if (!validFile(pendingPath)) return failSave("written_config_invalid");
    if (!LittleFS.rename(pendingPath, configPath)) return failSave("config_commit_failed");
    validConfig.store(true);
    saveSucceeded.store(true);
    lastError.store("none");
    return true;
}

bool protectedStoreLoad(AppConfig& config) {
    Lock lock;
    if (!filesystemMounted.load()) return false;
    if (!LittleFS.exists(configPath)) return protectedStoreSave(config);
    validConfig.store(validFile(configPath));
    if (!validConfig.load()) {
        lastError.store("existing_config_invalid");
        return false;
    }
    loadingTask.store(xTaskGetCurrentTaskHandle());
    const bool loaded = realStoreLoad(config);
    loadingTask.store(nullptr);
    lastError.store(loaded ? "none" : "backend_load_failed");
    return loaded;
}

fs::File protectedStoreOpen(fs::FS* filesystem, const char* path, const char* mode, bool create) {
    const bool configWrite = filesystem == static_cast<fs::FS*>(&LittleFS) && path && mode &&
        strcmp(path, configPath) == 0 && (strchr(mode, 'w') || strchr(mode, 'a') || strchr(mode, '+'));
    if (configWrite) {
        const auto task = xTaskGetCurrentTaskHandle();
        if (loadingTask.load() == task) return fs::File();
        if (writingTask.load() == task) return realStoreOpen(filesystem, pendingPath, mode, create);
    }
    return realStoreOpen(filesystem, path, mode, create);
}

bool protectedStoreFormat(fs::LittleFSFS* filesystem) {
    if (filesystem == &LittleFS && loadingTask.load() == xTaskGetCurrentTaskHandle()) return false;
    return realStoreFormat(filesystem);
}
void protectedStoreReboot(unsigned long delayMs) {
    if (!blockScheduledChange()) realStoreReboot(delayMs);
}
void protectedStoreApply() {
    if (!blockScheduledChange()) realStoreApply();
}
#endif
