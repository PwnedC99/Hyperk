"""Stable identity for the firmware source tree and selected build options."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

Import("env")
root = Path(env.subst("$PROJECT_DIR"))

def git(*arguments):
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""

def portable(value):
    if isinstance(value, (tuple, list)):
        return [portable(item) for item in value]
    return env.subst(str(value)).replace(str(root), "<PROJECT>")

commit = git("rev-parse", "HEAD") or "unknown"
dirty = bool(git("status", "--porcelain"))
digest = hashlib.sha256()
files = []
for directory in ["src", "include", "data", "effects", "scripts"]:
    files.extend(path for path in (root / directory).rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts and "backend" not in path.relative_to(root).parts)
files.extend(root / name for name in ["platformio.ini", "version", "requirements-build.txt", "resources/backend_checksums.json"])
for path in sorted(set(files)):
    if path.is_file():
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
metadata = {
    "version": (root / "version").read_text().strip(),
    "environment": env["PIOENV"],
    "backend_environment": env.GetProjectOption("custom_backend_env", env["PIOENV"]),
    "git_commit": commit,
    "git_dirty": dirty,
    "source_sha256": digest.hexdigest(),
    "build_flags": portable(env.get("BUILD_FLAGS", [])),
    "build_src_flags": portable(env.GetProjectOption("build_src_flags", [])),
}
identity = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:10]
metadata["build_id"] = f"{commit[:8]}{'-dirty' if dirty else ''}-{identity}"
env["HYPERK_BUILD_METADATA"] = metadata
generated = Path(env.subst("$BUILD_DIR")) / "generated_files"
generated.mkdir(parents=True, exist_ok=True)
(generated / "build_info.h").write_text("#pragma once" + chr(10) + "#define HYPERK_BUILD_ID " + json.dumps(metadata["build_id"]) + chr(10))
print(f">>> Build identity: {metadata['build_id']}")
