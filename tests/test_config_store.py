"""Inject filesystem failures into the production configuration store."""
from pathlib import Path
import re
import json
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JSON_HEADERS = ROOT / ".pio/libdeps/esp32s3-fh4r2/ArduinoJson/src"


class ConfigStoreLinkTests(unittest.TestCase):
    def test_all_store_wrappers_are_enabled_in_the_custom_profile(self):
        source = (ROOT / "src/config_store.cpp").read_text()
        wrappers = set(re.findall(r'asm\("__wrap_([^\"]+)"\)', source))
        originals = set(re.findall(r'asm\("__real_([^\"]+)"\)', source))
        custom = (ROOT / "platformio.ini").read_text().split("[env:esp32s3-fh4r2]", 1)[1].split("[env:", 1)[0]
        flags = set(re.findall(r"-Wl,--wrap=(\S+)", custom))
        self.assertEqual(len(wrappers), 8)
        self.assertEqual(wrappers, originals)
        self.assertTrue(wrappers.issubset(flags))


@unittest.skipUnless((JSON_HEADERS / "ArduinoJson.h").is_file(), "Build the FH4R2 profile first to install ArduinoJson")
class ConfigStoreTests(unittest.TestCase):
    def test_fault_injection_scenarios(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / "freertos").mkdir()
            (p / "LittleFS.h").write_text(r'''#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <map>
#include <memory>
#include <string>
namespace fs {
struct File {
    struct Handle { std::shared_ptr<std::string> data; size_t position = 0; };
    std::shared_ptr<Handle> handle;
    File() = default;
    explicit File(std::shared_ptr<std::string> data) : handle(std::make_shared<Handle>(Handle{data, 0})) {}
    explicit operator bool() const { return bool(handle); }
    size_t size() const { return handle ? handle->data->size() : 0; }
    int available() const { return handle && handle->position < size(); }
    int read() { return available() ? uint8_t((*handle->data)[handle->position++]) : -1; }
    size_t readBytes(char* buffer, size_t length) {
        size_t count = 0;
        while (count < length && available()) buffer[count++] = read();
        return count;
    }
    size_t write(const uint8_t* data, size_t size) { handle->data->append(reinterpret_cast<const char*>(data), size); return size; }
    void flush() {}
    void close() { handle.reset(); }
};
struct FS {
    std::map<std::string, std::shared_ptr<std::string>> files;
    File open(const char*, const char* mode = "r", bool create = false);
    bool remove(const char* path);
    bool rename(const char* from, const char* to);
    bool exists(const char* path) { return files.count(path); }
};
struct LittleFSFS : FS {
    bool mountWorks = true;
    int formats = 0;
    bool begin(bool formatOnFail) { return mountWorks; }
    bool format();
};
}
inline fs::LittleFSFS LittleFS;
''')
            (p / "freertos/FreeRTOS.h").write_text(r'''#pragma once
using TickType_t = unsigned;
constexpr TickType_t portMAX_DELAY = ~0u;
''')
            (p / "freertos/task.h").write_text(r'''#pragma once
using TaskHandle_t = void*;
inline thread_local TaskHandle_t currentTask = reinterpret_cast<void*>(1);
inline TaskHandle_t xTaskGetCurrentTaskHandle() { return currentTask; }
''')
            (p / "freertos/semphr.h").write_text(r'''#pragma once
#include <cassert>
#include <mutex>
struct StaticSemaphore_t { std::recursive_mutex gate; int depth = 0; };
using SemaphoreHandle_t = StaticSemaphore_t*;
inline SemaphoreHandle_t xSemaphoreCreateRecursiveMutexStatic(StaticSemaphore_t* value) { return value; }
inline int xSemaphoreTakeRecursive(SemaphoreHandle_t value, unsigned) { value->gate.lock(); ++value->depth; return 1; }
inline int xSemaphoreGiveRecursive(SemaphoreHandle_t value) { assert(value->depth > 0); --value->depth; value->gate.unlock(); return 1; }
''')
            (p / "esp_partition.h").write_text(r'''#pragma once
#include <cstddef>
#include <cstring>
constexpr int ESP_PARTITION_TYPE_DATA = 1, ESP_PARTITION_SUBTYPE_DATA_SPIFFS = 0x82, ESP_OK = 0;
struct esp_partition_t { size_t size = 4096; };
inline esp_partition_t partition;
inline bool erased = false, partitionMissing = false, readFails = false;
inline const esp_partition_t* esp_partition_find_first(int, int, const char*) { return partitionMissing ? nullptr : &partition; }
inline int esp_partition_read(const esp_partition_t*, size_t, void* buffer, size_t size) {
    memset(buffer, erased ? 0xff : 0, size); return readFails ? -1 : ESP_OK;
}
''')
            (p / "test.cpp").write_text(r'''#include <cassert>
#include <iostream>
#include <stdexcept>
#include <future>
#include <chrono>
#include <string>
class AppConfig { public: std::string payload; };
#include "config_store.cpp"
const std::string oldConfig = R"(__OLD_CONFIG__)";
const std::string newConfig = R"(__NEW_CONFIG__)";
bool openFails = false, shortWrite = false, renameFails = false, removeFails = false, nativeLoadFails = false;
bool syncFails = false;
bool ConfigStore::syncFile(const char*) { return !syncFails; }
bool backupOpenFails = false, commitRenameFails = false, interrupted = false, interruptedAfterCommit = false;
int nativeLoads = 0, reboots = 0, applies = 0;
std::promise<void> runtimeEntered, releaseRuntime;
std::future<void> runtimeRelease = releaseRuntime.get_future();
AppConfig activeConfig{oldConfig};
bool realConfigSave(const AppConfig& config) { activeConfig = config; return protectedStoreSave(activeConfig); }
bool Config::loadConfig() { return protectedStoreLoad(activeConfig); }
fs::File fs::FS::open(const char* path, const char* mode, bool create) { return protectedStoreOpen(this, path, mode, create); }
bool fs::FS::remove(const char* path) { if (removeFails) return false; files.erase(path); return true; }
bool fs::FS::rename(const char* from, const char* to) {
    if (renameFails || !files.count(from)) return false;
    if (std::string(from) == pendingPath && interrupted) throw std::runtime_error("power_loss_before_commit");
    if (std::string(from) == pendingPath && commitRenameFails) return false;
    files[to] = files[from]; files.erase(from);
    if (std::string(from) == pendingPath && interruptedAfterCommit) throw std::runtime_error("power_loss_after_commit");
    return true;
}
bool fs::LittleFSFS::format() { return protectedStoreFormat(this); }
fs::File realStoreOpen(fs::FS* filesystem, const char* path, const char* mode, bool) {
    if (strchr(mode, 'w')) {
        if (openFails || (backupOpenFails && std::string(path) == backupPendingPath)) return fs::File();
        filesystem->files[path] = std::make_shared<std::string>();
    }
    return filesystem->files.count(path) ? fs::File(filesystem->files[path]) : fs::File();
}
bool realStoreFormat(fs::LittleFSFS* fs) { ++fs->formats; fs->files.clear(); fs->mountWorks = true; return true; }
bool realStoreSave(const AppConfig& config) {
    auto file = LittleFS.open("/config.json", "w");
    if (!file) return false;
    const auto length = shortWrite ? config.payload.size() / 2 : config.payload.size();
    file.write(reinterpret_cast<const uint8_t*>(config.payload.data()), length);
    file.close();
    return true;
}
bool realStoreLoad(AppConfig& config) {
    ++nativeLoads;
    if (nativeLoadFails) {
        assert(!LittleFS.format());
        assert(!LittleFS.open("/config.json", "w"));
        return false;
    }
    config.payload = *LittleFS.files.at("/config.json");
    return true;
}
void realStoreReboot(unsigned long) { ++reboots; }
void realStoreApply() { ++applies; }
void realDeviceReboot() { ++reboots; }
std::string saved() { return *LittleFS.files.at("/config.json"); }
void checkFailedRequest(const AppConfig& config, const char* error) {
    ConfigStore::beginRequest();
    assert(!protectedStoreSave(config));
    assert(ConfigStore::requestFailed() && !ConfigStore::lastSaveSucceeded());
    assert(std::string(ConfigStore::error()) == error);
    protectedStoreReboot(500); protectedStoreApply();
    assert(reboots == 0 && applies == 0 && saved() == oldConfig);
    currentTask = reinterpret_cast<void*>(2);
    protectedStoreReboot(1); assert(reboots == 1); reboots = 0;
    currentTask = reinterpret_cast<void*>(1);
    ConfigStore::endRequest();
}
int main(int argc, char** argv) {
    assert(argc == 2);
    const std::string scenario = argv[1];
    AppConfig config{oldConfig}, next{newConfig};
    erased = true; LittleFS.mountWorks = false;
    assert(ConfigStore::begin() && LittleFS.formats == 1);
    assert(protectedStoreLoad(config) && saved() == oldConfig && ConfigStore::configValid());
    if (scenario == "schema_and_reload") {
        JsonDocument doc; assert(!deserializeJson(doc, oldConfig));
        assert(!doc["numLeds"].is<unsigned>() && doc["led"]["numLeds"].as<unsigned>() == 258);
        AppConfig afterRestart;
        assert(protectedStoreLoad(afterRestart) && afterRestart.payload == oldConfig);
    } else if (scenario == "save_restart_repeat") {
        const auto initialHash = ConfigStore::publicChecksum();
        assert(protectedConfigSave(next) && saved() == newConfig);
        assert(ConfigStore::publicChecksum() != initialHash);
        for (int i = 0; i < 8; ++i) {
            const auto& expected = i % 2 ? oldConfig : newConfig;
            assert(protectedConfigSave(AppConfig{expected}));
            AppConfig afterRestart;
            assert(ConfigStore::begin() && protectedStoreLoad(afterRestart));
            assert(afterRestart.payload == expected && saved() == expected);
        }
    } else if (scenario == "short_write_and_ram_restore") {
        shortWrite = true;
        assert(!protectedConfigSave(next) && activeConfig.payload == oldConfig);
        checkFailedRequest(next, "written_config_invalid");
    } else if (scenario == "invalid_json_and_values") {
        for (const auto& payload : {std::string("{}"), newConfig + "garbage", newConfig.substr(0, 20)})
            checkFailedRequest(AppConfig{payload}, "written_config_invalid");
        JsonDocument doc; assert(!deserializeJson(doc, newConfig));
        doc["led"]["numLeds"] = 0;
        std::string invalid; serializeJson(doc, invalid);
        checkFailedRequest(AppConfig{invalid}, "written_config_invalid");
        doc["led"]["numLeds"] = 258; doc["segments"][1]["startIndex"] = 258;
        invalid.clear(); serializeJson(doc, invalid);
        checkFailedRequest(AppConfig{invalid}, "written_config_invalid");
    } else if (scenario == "flash_open_failure") {
        openFails = true; checkFailedRequest(next, "backend_write_failed");
    } else if (scenario == "flash_sync_failure") {
        syncFails = true; checkFailedRequest(next, "config_sync_failed");
    } else if (scenario == "backup_and_commit_failure") {
        backupOpenFails = true; checkFailedRequest(next, "config_backup_failed"); backupOpenFails = false;
        commitRenameFails = true; checkFailedRequest(next, "config_commit_failed"); commitRenameFails = false;
        removeFails = true; checkFailedRequest(next, "pending_cleanup_failed");
    } else if (scenario == "interrupted_before_commit" || scenario == "interrupted_after_commit") {
        interrupted = scenario == "interrupted_before_commit";
        interruptedAfterCommit = !interrupted;
        try { protectedStoreSave(next); assert(false); } catch (const std::runtime_error&) {}
        interrupted = interruptedAfterCommit = false;
        AppConfig afterRestart;
        assert(ConfigStore::begin() && protectedStoreLoad(afterRestart));
        assert(afterRestart.payload == (scenario == "interrupted_before_commit" ? oldConfig : newConfig));
    } else if (scenario == "recover_previous") {
        assert(protectedStoreSave(next));
        *LittleFS.files.at(configPath) = "broken-json";
        AppConfig afterRestart;
        assert(ConfigStore::begin() && protectedStoreLoad(afterRestart));
        assert(afterRestart.payload == oldConfig && saved() == oldConfig && LittleFS.formats == 1);
    } else if (scenario == "retain_invalid_without_backup") {
        *LittleFS.files.at(configPath) = "broken-json";
        assert(!protectedStoreLoad(config) && saved() == "broken-json" && LittleFS.formats == 1);
        assert(std::string(ConfigStore::error()) == "existing_config_invalid");
        assert(!ConfigStore::beginLedInit());
    } else if (scenario == "native_format_protection") {
        nativeLoadFails = true;
        assert(!protectedStoreLoad(config) && saved() == oldConfig && LittleFS.formats == 1);
        assert(std::string(ConfigStore::error()) == "backend_load_failed");
    } else if (scenario == "led_boot_guard_and_driver_config") {
        assert(ConfigStore::beginLedInit());
        assert(ConfigStore::begin() && ConfigStore::ledRecovery() && !ConfigStore::beginLedInit());
        assert(protectedStoreSave(next) && ConfigStore::beginLedInit());
        ConfigStore::endLedInit(false);
        assert(ConfigStore::ledRecovery());
        for (bool rmt : {true, false}) {
            JsonDocument doc; assert(!deserializeJson(doc, newConfig));
            doc["quirks"]["disableSpiEmulation"] = rmt;
            std::string payload; serializeJson(doc, payload);
            assert(protectedStoreSave(AppConfig{payload}));
            assert(ConfigStore::beginLedInit()); ConfigStore::endLedInit(true);
            assert(!ConfigStore::ledRecovery());
            AppConfig reloaded; assert(protectedStoreLoad(reloaded));
            JsonDocument result; assert(!deserializeJson(result, reloaded.payload));
            assert(result["quirks"]["disableSpiEmulation"].as<bool>() == rmt);
            assert(result["led"]["numLeds"].as<unsigned>() == 258);
            assert(result["segments"][0]["data"].as<int>() == 37 && result["segments"][1]["data"].as<int>() == 38);
        }
    } else if (scenario == "mount_failures_and_foreign_files") {
        auto other = LittleFS.open("/presets.json", "w"); assert(other && LittleFS.exists("/presets.json"));
        fs::FS otherFS; auto file = otherFS.open(configPath, "w"); assert(file && otherFS.exists(configPath));
        erased = false; LittleFS.mountWorks = false;
        assert(!ConfigStore::begin() && saved() == oldConfig && LittleFS.formats == 1);
        assert(!protectedStoreSave(next) && std::string(ConfigStore::error()) == "filesystem_not_mounted");
        erased = true; readFails = true;
        assert(!ConfigStore::begin() && LittleFS.formats == 1);
        readFails = false; partitionMissing = true;
        assert(!ConfigStore::begin() && LittleFS.formats == 1);
    } else if (scenario == "concurrent_save_waits_for_runtime") {
        auto runtime = std::async(std::launch::async, [] {
            currentTask = reinterpret_cast<void*>(2);
            ConfigStore::runLocked([] { runtimeEntered.set_value(); runtimeRelease.wait(); });
        });
        runtimeEntered.get_future().wait();
        auto writer = std::async(std::launch::async, [] { return protectedConfigSave(AppConfig{newConfig}); });
        assert(writer.wait_for(std::chrono::milliseconds(20)) == std::future_status::timeout);
        releaseRuntime.set_value(); runtime.get();
        assert(writer.get() && saved() == newConfig);
    } else if (scenario == "concurrent_reboot_waits_for_request") {
        ConfigStore::beginRequest();
        auto reboot = std::async(std::launch::async, [] {
            currentTask = reinterpret_cast<void*>(2);
            protectedDeviceReboot();
        });
        assert(reboot.wait_for(std::chrono::milliseconds(20)) == std::future_status::timeout);
        assert(protectedStoreSave(next));
        ConfigStore::endRequest(); reboot.get();
        assert(reboots == 1 && saved() == newConfig);
    } else if (scenario == "scheduling_and_secret_free_checksum") {
        ConfigStore::beginRequest(); assert(protectedStoreSave(next));
        protectedStoreReboot(500); protectedStoreApply(); ConfigStore::endRequest();
        assert(reboots == 1 && applies == 1);
        const auto hash = ConfigStore::publicChecksum();
        JsonDocument doc; assert(!deserializeJson(doc, newConfig));
        doc["wifi"]["ssid"] = "different-example"; doc["wifi"]["pass"] = "different-example";
        std::string payload; serializeJson(doc, payload);
        assert(protectedStoreSave(AppConfig{payload}) && ConfigStore::publicChecksum() == hash);
    } else assert(false);
}

'''.replace('__OLD_CONFIG__', (ROOT / 'tests/fixtures/config_0_0_5.json').read_text()).replace('__NEW_CONFIG__', json.dumps(dict(json.loads((ROOT / 'tests/fixtures/config_0_0_5.json').read_text()), deviceName='hyperk-test'))))
            command = [shutil.which("c++"), "-std=c++17", "-pthread", "-DHYPERK_CONFIG_STORE",
                       "-I" + str(p), "-I" + str(JSON_HEADERS), "-I" + str(ROOT / "src"),
                       "-I" + str(ROOT / "include"), str(p / "test.cpp"), "-o", str(p / "test")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            scenarios = ["schema_and_reload", "save_restart_repeat", "short_write_and_ram_restore",
                         "invalid_json_and_values", "flash_open_failure", "flash_sync_failure", "backup_and_commit_failure",
                         "interrupted_before_commit", "interrupted_after_commit", "recover_previous",
                         "retain_invalid_without_backup", "native_format_protection",
                         "led_boot_guard_and_driver_config", "mount_failures_and_foreign_files",
                         "scheduling_and_secret_free_checksum", "concurrent_save_waits_for_runtime",
                         "concurrent_reboot_waits_for_request"]
            for scenario in scenarios:
                with self.subTest(scenario=scenario):
                    subprocess.run([str(p / "test"), scenario], check=True, timeout=10)


if __name__ == "__main__":
    if not (JSON_HEADERS / "ArduinoJson.h").is_file():
        raise SystemExit("Build esp32s3-fh4r2 first to install the pinned ArduinoJson headers")
    unittest.main()
