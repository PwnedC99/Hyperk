import pathlib
import runpy
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
class MetadataTests(unittest.TestCase):
    def test_identity_tracks_source_and_flags_and_generates_a_valid_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/"src").mkdir()
            (root/"src/main.cpp").write_text("initial")
            (root/"version").write_text("0.0.5")
            class Env(dict):
                def subst(self, value):
                    return {"$PROJECT_DIR": str(root), "$BUILD_DIR": str(root/"build")}.get(value, value)
                def GetProjectOption(self, name, default=None):
                    return self.get("SRC_BUILD_FLAGS", []) if name == "build_src_flags" else default
            def generate(flags):
                env = Env(PIOENV="esp32s3-fh4r2", BUILD_FLAGS=["-DTEST=1"], SRC_BUILD_FLAGS=flags)
                def git(arguments, **kwargs):
                    return types.SimpleNamespace(returncode=0, stdout="f83984b2" if arguments[-1] == "HEAD" else "")
                with patch("subprocess.run", git), patch("builtins.print"):
                    runpy.run_path(str(ROOT/"scripts/build_metadata.py"), init_globals={"env": env, "Import": lambda name: None})
                return env["HYPERK_BUILD_METADATA"]["build_id"]
            first = generate([])
            self.assertEqual(first, generate([]))
            self.assertNotEqual(first, generate(["-DWIFI_TX_POWER_DBM=17"]))
            header = (root/"build/generated_files/build_info.h").read_text()
            self.assertTrue(header.startswith("#pragma once\n#define HYPERK_BUILD_ID "))
            self.assertNotIn("\\n", header)
            (root/"src/main.cpp").write_text("changed")
            self.assertNotEqual(first, generate([]))
