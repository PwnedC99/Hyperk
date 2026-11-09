"""Check that sync/close failures reach the transaction caller."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConfigSyncTests(unittest.TestCase):
    def test_checked_sync_and_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            source = path / "test.cpp"
            source.write_text(r'''#include <cassert>
#include <string>
#include "config_store_sync.cpp"
bool openFails = false, syncFails = false, closeFails = false;
int closes = 0;
extern "C" int __wrap_open(const char* path, int flags, ...) {
    assert(std::string(path) == "/littlefs/config.pending.json" && flags == O_RDONLY);
    return openFails ? -1 : 42;
}
extern "C" int __wrap_fsync(int fd) { assert(fd == 42); return syncFails ? -1 : 0; }
extern "C" int __wrap_close(int fd) { assert(fd == 42); ++closes; return closeFails ? -1 : 0; }
int main() {
    assert(ConfigStore::syncFile("/config.pending.json") && closes == 1);
    syncFails = true; assert(!ConfigStore::syncFile("/config.pending.json") && closes == 2);
    syncFails = false; closeFails = true;
    assert(!ConfigStore::syncFile("/config.pending.json") && closes == 3);
    closeFails = false; openFails = true;
    assert(!ConfigStore::syncFile("/config.pending.json") && closes == 3);
    assert(!ConfigStore::syncFile(std::string(200, 'x').c_str()));
}
''')
            result = subprocess.run([
                shutil.which("c++"), "-std=c++17", "-DHYPERK_CONFIG_STORE",
                "-I" + str(ROOT / "src"), "-I" + str(ROOT / "include"), str(source),
                "-Wl,--wrap=open", "-Wl,--wrap=fsync", "-Wl,--wrap=close", "-o", str(path / "test")
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(path / "test")], check=True)


if __name__ == "__main__":
    unittest.main()
