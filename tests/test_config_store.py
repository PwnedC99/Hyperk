"""Inject filesystem failures into the production configuration store."""
from pathlib import Path
import re
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
        self.assertEqual(len(wrappers), 7)
        self.assertEqual(wrappers, originals)
        self.assertTrue(wrappers.issubset(flags))


@unittest.skipUnless((JSON_HEADERS / "ArduinoJson.h").is_file(), "Build the FH4R2 profile first to install ArduinoJson")
class ConfigStoreTests(unittest.TestCase):
    def test_transactions_loading_format_protection_and_http_scheduling(self):
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
inline TaskHandle_t currentTask = reinterpret_cast<void*>(1);
inline TaskHandle_t xTaskGetCurrentTaskHandle() { return currentTask; }
''')
            (p / "freertos/semphr.h").write_text(r'''#pragma once
#include <cassert>
struct StaticSemaphore_t { int depth = 0; };
using SemaphoreHandle_t = StaticSemaphore_t*;
inline SemaphoreHandle_t xSemaphoreCreateRecursiveMutexStatic(StaticSemaphore_t* value) { return value; }
inline int xSemaphoreTakeRecursive(SemaphoreHandle_t value, unsigned) { ++value->depth; return 1; }
inline int xSemaphoreGiveRecursive(SemaphoreHandle_t value) { assert(value->depth > 0); --value->depth; return 1; }
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
#include <string>
class AppConfig { public: std::string payload; };
#include "config_store.cpp"
const std::string oldConfig = R"({"wifi":{"ssid":"old","password":"secret"},"segments":[],"numLeds":258})";
const std::string newConfig = R"({"wifi":{"ssid":"new","password":"secret"},"segments":[],"numLeds":258})";
bool openFails = false, shortWrite = false, renameFails = false, removeFails = false, nativeLoadFails = false;
int nativeLoads = 0, reboots = 0, applies = 0;
AppConfig activeConfig{oldConfig};
bool realConfigSave(const AppConfig& config) { activeConfig = config; return protectedStoreSave(activeConfig); }
bool Config::loadConfig() { return protectedStoreLoad(activeConfig); }
fs::File fs::FS::open(const char* path, const char* mode, bool create) { return protectedStoreOpen(this, path, mode, create); }
bool fs::FS::remove(const char* path) { if (removeFails) return false; files.erase(path); return true; }
bool fs::FS::rename(const char* from, const char* to) {
    if (renameFails || !files.count(from)) return false;
    files[to] = files[from]; files.erase(from); return true;
}
bool fs::LittleFSFS::format() { return protectedStoreFormat(this); }
fs::File realStoreOpen(fs::FS* filesystem, const char* path, const char* mode, bool) {
    if (strchr(mode, 'w')) {
        if (openFails) return fs::File();
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
int main() {
    AppConfig config{oldConfig}, next{newConfig};
    erased = true; LittleFS.mountWorks = false;
    assert(ConfigStore::begin() && LittleFS.formats == 1);
    assert(protectedStoreLoad(config) && saved() == oldConfig && ConfigStore::configValid());
    AppConfig loaded;
    assert(protectedStoreLoad(loaded) && loaded.payload == oldConfig && nativeLoads == 1);
    shortWrite = true;
    assert(!protectedConfigSave(next) && activeConfig.payload == oldConfig);
    assert(std::string(ConfigStore::error()) == "written_config_invalid");
    nativeLoads = 1;
    checkFailedRequest(next, "written_config_invalid"); shortWrite = false;
    checkFailedRequest(AppConfig{"{}"}, "written_config_invalid");
    checkFailedRequest(AppConfig{newConfig + "garbage"}, "written_config_invalid");
    openFails = true; checkFailedRequest(next, "backend_write_failed"); openFails = false;
    renameFails = true; checkFailedRequest(next, "config_commit_failed"); renameFails = false;
    removeFails = true; checkFailedRequest(next, "pending_cleanup_failed"); removeFails = false;
    ConfigStore::beginRequest();
    assert(protectedStoreSave(next));
    assert(!ConfigStore::requestFailed() && ConfigStore::lastSaveSucceeded());
    protectedStoreReboot(500); protectedStoreApply();
    assert(reboots == 1 && applies == 1 && saved() == newConfig);
    assert(std::string(ConfigStore::error()) == "none");
    ConfigStore::endRequest();
    *LittleFS.files.at("/config.json") = "broken-json";
    assert(!protectedStoreLoad(loaded) && saved() == "broken-json" && nativeLoads == 1);
    assert(LittleFS.formats == 1 && std::string(ConfigStore::error()) == "existing_config_invalid");
    *LittleFS.files.at("/config.json") = oldConfig;
    nativeLoadFails = true;
    assert(!protectedStoreLoad(loaded) && saved() == oldConfig && LittleFS.formats == 1);
    assert(std::string(ConfigStore::error()) == "backend_load_failed");
    nativeLoadFails = false;
    auto other = LittleFS.open("/presets.json", "w"); assert(other && LittleFS.exists("/presets.json"));
    fs::FS otherFS; auto file = otherFS.open("/config.json", "w"); assert(file && otherFS.exists("/config.json"));
    erased = false; LittleFS.mountWorks = false;
    assert(!ConfigStore::begin() && saved() == oldConfig && LittleFS.formats == 1);
    assert(!protectedStoreSave(next) && std::string(ConfigStore::error()) == "filesystem_not_mounted");
    erased = true; readFails = true;
    assert(!ConfigStore::begin() && LittleFS.formats == 1);
    readFails = false; partitionMissing = true;
    assert(!ConfigStore::begin() && LittleFS.formats == 1);
}
''')
            command = [shutil.which("c++"), "-std=c++17", "-DHYPERK_CONFIG_STORE",
                       "-I" + str(p), "-I" + str(JSON_HEADERS), "-I" + str(ROOT / "src"),
                       "-I" + str(ROOT / "include"), str(p / "test.cpp"), "-o", str(p / "test")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(p / "test")], check=True)


if __name__ == "__main__":
    if not (JSON_HEADERS / "ArduinoJson.h").is_file():
        raise SystemExit("Build esp32s3-fh4r2 first to install the pinned ArduinoJson headers")
    unittest.main()
