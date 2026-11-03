"""Verified, atomic downloads. This module is independent of PlatformIO."""
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.request import urlopen


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_backend(url, destination, expected_sha256, opener=urlopen):
    destination = Path(destination)
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("A valid, pinned backend SHA-256 is required")
    if destination.is_file() and sha256_file(destination) == expected_sha256:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=destination.name+".", suffix=".part", delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            with opener(url, timeout=30) as response:
                for chunk in iter(lambda: response.read(65536), b""):
                    output.write(chunk)
                    digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest() != expected_sha256:
            raise ValueError("Backend SHA-256 mismatch; downloaded file was not accepted")
        os.replace(temporary, destination)
        temporary = None
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
