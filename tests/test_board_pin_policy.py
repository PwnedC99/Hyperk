import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
class BoardPinPolicyTests(unittest.TestCase):
    def test_reservation_and_malformed_segment_requests(self):
        source = r"""#include <cassert>
#include "board_pin_policy.h"
int main() {
    using BoardPinPolicy::invalidSegments;
    assert(!invalidSegments("0,37,38,0", 1));
    assert(!invalidSegments("1,37,0,1,50,38,0,0", 1));
    assert(invalidSegments("0,1,38,0", 1));
    assert(invalidSegments("0,37,1,0", 1));
    assert(invalidSegments("0,257,0,0", 1));
    assert(invalidSegments("0,4294967297,0,0", 1));
    assert(invalidSegments("0,37,0", 1));
    assert(invalidSegments("0,37,0,0,", 1));
    assert(invalidSegments("0,37,0,0x", 1));
    assert(invalidSegments("", 1));
}
"""
        with tempfile.TemporaryDirectory() as directory:
            p = pathlib.Path(directory)
            (p/"test.cpp").write_text(source)
            result = subprocess.run([shutil.which("c++"), "-std=c++17", "-I"+str(ROOT/"include"),
                str(p/"test.cpp"), "-o", str(p/"test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(p/"test")], check=True)
