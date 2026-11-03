import hashlib
import io
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from backend_download import ensure_backend

DATA = b"!<arch>\ncomplete backend"
SHA = hashlib.sha256(DATA).hexdigest()

class BackendDownloadTests(unittest.TestCase):
    def test_verified_cache_needs_no_network(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)/"backend.a"
            target.write_bytes(DATA)
            def offline(*args, **kwargs): raise AssertionError("Network must not be used")
            self.assertFalse(ensure_backend("url", target, SHA, offline))

    def test_invalid_cache_is_replaced_only_by_verified_download(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)/"backend.a"
            target.write_bytes(b"broken")
            self.assertTrue(ensure_backend("url", target, SHA, lambda *a, **kw: io.BytesIO(DATA)))
            self.assertEqual(target.read_bytes(), DATA)
            self.assertEqual(list(target.parent.glob("*.part")), [])

    def test_checksum_mismatch_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)/"backend.a"
            target.write_bytes(b"old")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                ensure_backend("url", target, SHA, lambda *a, **kw: io.BytesIO(b"truncated"))
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual(list(target.parent.glob("*.part")), [])

    def test_interrupted_download_never_becomes_a_cached_library(self):
        class Interrupted(io.BytesIO):
            def read(self, size=-1):
                if self.tell(): raise OSError("Connection interrupted")
                return super().read(size)
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)/"backend.a"
            with self.assertRaises(OSError):
                ensure_backend("url", target, SHA, lambda *a, **kw: Interrupted(DATA[:6]))
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.glob("*.part")), [])

    def test_missing_checksum_fails_before_network(self):
        with self.assertRaises(ValueError): ensure_backend("url", "unused.a", "")
