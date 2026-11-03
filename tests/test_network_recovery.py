import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
class NetworkRecoveryTests(unittest.TestCase):
    def test_reconnect_ap_clients_and_timer_wrap(self):
        source = r"""#include <cassert>
#include <cstdint>
#include "network_recovery.h"
using namespace NetworkRecovery;
int main() {
    Policy p;
    p.begin(false, false, 0);
    assert(p.poll(600000, false, true, false) == Action::None);
    p.begin(true, true, 0);
    assert(p.poll(100, false, false, false) == Action::Retry);
    assert(p.poll(101, false, false, false) == Action::None);
    assert(p.poll(100 + WIFI_RETRY_INTERVAL_MS, false, false, false) == Action::Retry);
    assert(p.poll(100 + WIFI_AP_FALLBACK_MS, false, false, false) == Action::StartAP);
    assert(p.poll(100000, false, true, true) == Action::None);
    assert(p.poll(100001, false, true, false) == Action::Retry);
    assert(p.poll(100002, true, true, false) == Action::CloseAP);
    assert(p.poll(100003, true, false, false) == Action::None);
    assert(p.poll(100004, false, false, false) == Action::Retry);
    p.begin(true, false, UINT32_MAX - 1000);
    const uint32_t retryTime = uint32_t(UINT32_MAX - 1000 + uint32_t(WIFI_RETRY_INTERVAL_MS));
    assert(p.poll(retryTime - 1, false, true, false) == Action::None);
    assert(p.poll(retryTime, false, true, false) == Action::Retry);
    p.begin(true, false, 0);
    assert(p.poll(WIFI_RETRY_INTERVAL_MS, false, true, true) == Action::None);
    assert(p.poll(WIFI_RETRY_INTERVAL_MS + 1, false, true, false) == Action::Retry);
}
"""
        with tempfile.TemporaryDirectory() as directory:
            p = pathlib.Path(directory)
            (p/"test.cpp").write_text(source)
            result = subprocess.run([shutil.which("c++"), "-std=c++17", "-I"+str(ROOT/"include"),
                str(p/"test.cpp"), "-o", str(p/"test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(p/"test")], check=True)
