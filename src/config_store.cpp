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
#include "config_diagnostics.h"

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
void realDeviceReboot() asm("__real__ZN5Utils12rebootDeviceEv");
bool protectedStoreSave(const AppConfig&) asm("__wrap__ZN7Storage10saveConfigERK9AppConfig");
bool protectedStoreLoad(AppConfig&) asm("__wrap__ZN7Storage10loadConfigER9AppConfig");
fs::File protectedStoreOpen(fs::FS*, const char*, const char*, bool) asm("__wrap__ZN2fs2FS4openEPKcS2_b");
bool protectedStoreFormat(fs::LittleFSFS*) asm("__wrap__ZN2fs10LittleFSFS6formatEv");
void protectedStoreReboot(unsigned long) asm("__wrap__ZN7Manager14scheduleRebootEm");
void protectedStoreApply() asm("__wrap__ZN7Manager19scheduleApplyConfigEv");
void protectedDeviceReboot() asm("__wrap__ZN5Utils12rebootDeviceEv");

namespace {
    constexpr char configPath[] = "/config.json";
    constexpr char pendingPath[] = "/config.pending.json";
    constexpr char previousPath[] = "/config.previous.json";
    constexpr char backupPendingPath[] = "/config.previous.pending.json";
    constexpr char ledPendingPath[] = "/config.led-init";
    std::atomic<bool> filesystemMounted{false}, validConfig{false}, saveSucceeded{false}, attemptedSave{false};
    std::atomic<const char*> lastError{"not_checked"};
    std::atomic<TaskHandle_t> writingTask{nullptr}, loadingTask{nullptr}, requestTask{nullptr};
    std::atomic<uint32_t> publicHash{0};
    std::atomic<bool> ledBlocked{false};
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
        ConfigDiagnostics::event(reason);
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
        if (!(parsed && !trailingData && doc.is<JsonObject>() &&
            doc["wifi"].is<JsonObject>() && doc["segments"].is<JsonArray>() &&
            doc["led"].is<JsonObject>() && doc["led"]["numLeds"].is<unsigned int>())) return false;
        const unsigned count = doc["led"]["numLeds"].as<unsigned>();
        if (count == 0 || count > 2000 || !doc["led"]["type"].is<unsigned>() ||
            doc["led"]["type"].as<unsigned>() > 2) return false;
        const auto segments = doc["segments"].as<JsonArray>();
        if (segments.size() == 0 || segments.size() > 4) return false;
        int previous = -1;
        for (JsonObject segment : segments) {
            if (!segment["startIndex"].is<int>() || !segment["data"].is<int>()) return false;
            const int start = segment["startIndex"].as<int>(), pin = segment["data"].as<int>();
            if (start < 0 || start >= int(count) || start <= previous || (previous == -1 && start != 0) ||
                pin < 0 || pin > 48 || pin == 1 || pin == 19 || pin == 20) return false;
            previous = start;
        }
        return true;
    }
    bool copyVerified(const char* from, const char* temporary, const char* target) {
        auto source = LittleFS.open(from, "r");
        auto destination = LittleFS.open(temporary, "w");
        if (!source || !destination) return false;
        uint8_t buffer[256];
        while (source.available()) {
            const size_t length = source.readBytes(reinterpret_cast<char*>(buffer), sizeof(buffer));
            if (!length || destination.write(buffer, length) != length) return false;
        }
        destination.flush();
        destination.close();
        source.close();
        if (!ConfigStore::syncFile(temporary)) return false;
        if (!validFile(temporary)) return false;
        // Verify exact bytes, including fields not known by this adapter.
        source = LittleFS.open(from, "r");
        auto copy = LittleFS.open(temporary, "r");
        if (!source || !copy || source.size() != copy.size()) return false;
        while (source.available()) if (source.read() != copy.read()) return false;
        source.close(); copy.close();
        return LittleFS.rename(temporary, target);
    }
    void updatePublicHash() {
        auto file = LittleFS.open(configPath, "r");
        JsonDocument doc;
        if (!file || deserializeJson(doc, file)) return;
        file.close();
        // Exclude all credentials, including SSID, from the diagnostic checksum.
        doc.remove("wifi");
        struct HashWriter {
            uint32_t hash = 2166136261u;
            size_t write(uint8_t value) { hash = (hash ^ value) * 16777619u; return 1; }
            size_t write(const uint8_t* data, size_t length) {
                for (size_t i = 0; i < length; ++i) write(data[i]);
                return length;
            }
        } writer;
        serializeJson(doc, writer);
        publicHash.store(writer.hash);
        ConfigDiagnostics::event("[CONFIG] Public checksum (wifi excluded)", writer.hash);
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
    ledBlocked.store(ready && LittleFS.exists(ledPendingPath));
    lastError.store(ready ? "none" : "filesystem_mount_failed");
    ConfigDiagnostics::event("[BOOT] Filesystem mount result", ready);
    if (const auto* partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA,
        ESP_PARTITION_SUBTYPE_DATA_SPIFFS, "spiffs")) {
        ConfigDiagnostics::event("[BOOT] Filesystem partition size", partition->size);
    }
    return ready;
}
bool ConfigStore::mounted() { return filesystemMounted.load(); }
bool ConfigStore::configValid() { return validConfig.load(); }
bool ConfigStore::lastSaveSucceeded() { return saveSucceeded.load(); }
bool ConfigStore::saveAttempted() { return attemptedSave.load(); }
const char* ConfigStore::error() { return lastError.load(); }
uint32_t ConfigStore::publicChecksum() { return publicHash.load(); }
bool ConfigStore::ledRecovery() { return ledBlocked.load(); }
void ConfigStore::runLocked(void (*operation)()) {
    Lock lock;
    operation();
}
bool ConfigStore::beginLedInit() {
    Lock lock;
    if (!filesystemMounted.load() || !validConfig.load() || ledBlocked.load()) return false;
    auto marker = LittleFS.open(ledPendingPath, "w");
    const uint8_t value = 1;
    if (!marker || marker.write(&value, 1) != 1) return false;
    marker.flush(); marker.close();
    if (!syncFile(ledPendingPath)) return false;
    auto verify = LittleFS.open(ledPendingPath, "r");
    return verify && verify.size() == 1 && verify.read() == 1;
}
void ConfigStore::endLedInit(bool succeeded) {
    Lock lock;
    ledBlocked.store(!succeeded || !LittleFS.remove(ledPendingPath));
}
void ConfigStore::beginRequest() {
    xSemaphoreTakeRecursive(mutex(), portMAX_DELAY);
    failedRequest = false;
    requestTask.store(xTaskGetCurrentTaskHandle());
    ConfigDiagnostics::event("[CONFIG] Request received");
}
bool ConfigStore::requestFailed() { return failedRequest; }
void ConfigStore::endRequest() {
    requestTask.store(nullptr);
    xSemaphoreGiveRecursive(mutex());
}

bool protectedConfigSave(const AppConfig& config) {
    Lock lock;
    const bool saved = realConfigSave(config);
    ConfigDiagnostics::event("[CONFIG] RAM update and save result", saved);
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
    saveSucceeded.store(false);
    ConfigDiagnostics::event("[CONFIG] Storage write started");
    writingTask.store(xTaskGetCurrentTaskHandle());
    const bool written = realStoreSave(config);
    writingTask.store(nullptr);
    ConfigDiagnostics::event("[CONFIG] Backend write returned", written);
    if (!written) return failSave("backend_write_failed");
    if (!ConfigStore::syncFile(pendingPath)) return failSave("config_sync_failed");
    if (!validFile(pendingPath)) return failSave("written_config_invalid");
    ConfigDiagnostics::event("[CONFIG] Storage verification successful");
    if (validFile(configPath) && !copyVerified(configPath, backupPendingPath, previousPath))
        return failSave("config_backup_failed");
    if (!LittleFS.rename(pendingPath, configPath)) return failSave("config_commit_failed");
    if (!validFile(configPath)) return failSave("committed_config_invalid");
    validConfig.store(true);
    saveSucceeded.store(true);
    lastError.store("none");
    ledBlocked.store(false);
    updatePublicHash();
    ConfigDiagnostics::event("[CONFIG] Storage write completed");
    return true;
}

bool protectedStoreLoad(AppConfig& config) {
    Lock lock;
    if (!filesystemMounted.load()) return false;
    const bool exists = LittleFS.exists(configPath);
    validConfig.store(validFile(configPath));
    if (!validConfig.load()) {
        if (validFile(previousPath)) {
            if (!copyVerified(previousPath, pendingPath, configPath)) {
                lastError.store("config_recovery_failed");
                return false;
            }
            validConfig.store(true);
            ConfigDiagnostics::event("[CONFIG] Previous configuration recovered");
        } else if (!exists) return protectedStoreSave(config);
        else {
            lastError.store("existing_config_invalid");
            ConfigDiagnostics::event("[BOOT] Configuration invalid; retained");
            return false;
        }
    }
    loadingTask.store(xTaskGetCurrentTaskHandle());
    const bool loaded = realStoreLoad(config);
    loadingTask.store(nullptr);
    if (!loaded) validConfig.store(false);
    lastError.store(loaded ? "none" : "backend_load_failed");
    if (loaded) updatePublicHash();
    ConfigDiagnostics::event("[BOOT] Configuration load result", loaded);
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
    if (!blockScheduledChange()) {
        ConfigDiagnostics::event("[CONFIG] Restart scheduled", delayMs);
        realStoreReboot(delayMs);
    }
}
void protectedStoreApply() {
    if (!blockScheduledChange()) realStoreApply();
}
void protectedDeviceReboot() {
    Lock lock;
    realDeviceReboot();
}
#endif
