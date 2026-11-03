"""Verify the browser UI contract of the pinned, unchanged backend archive."""
import argparse
import json
from pathlib import Path
import re
import zlib
from backend_download import ensure_backend


def extract_ui(library, output):
    blob = Path(library).read_bytes()
    found = {}
    position = 0
    while True:
        position = blob.find(b"\x1f\x8b\x08", position)
        if position < 0: break
        try:
            decoder = zlib.decompressobj(31)
            text = decoder.decompress(blob[position:], 2_000_000).decode("utf-8")
            if not decoder.eof: raise ValueError("Incomplete asset")
            if "function setupPinValidator()" in text and "function setupLedHardware()" in text:
                found["settings_led_hardware.js"] = text
            elif '<form action="/save_config"' in text and "function setupPageControls(" in text:
                found["settings.html"] = text
            elif 'id="segmentContainer"' in text and 'id="ledType"' in text and "<html" not in text:
                found["settings_led_hardware.html"] = text
        except (zlib.error, UnicodeError, ValueError):
            pass
        position += 3
    expected = {"settings_led_hardware.js", "settings.html", "settings_led_hardware.html"}
    if set(found) != expected: raise ValueError("Backend UI layout changed; review the board extension")
    pattern = r'"ESP32-S3"\s*:\s*\{\s*gpio\s*:\s*\[([^\]]*)\]'
    if len(re.findall(pattern, found["settings_led_hardware.js"])) != 1:
        raise ValueError("Backend S3 GPIO contract changed")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, text in found.items(): (output/name).write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=(Path(__file__).resolve().parents[1]/"version").read_text().strip())
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    name = "libBackend_esp32s3.a"
    checksum = json.loads((root/"resources/backend_checksums.json").read_text())[arguments.version][name]
    library = root/"export_backend/precompiled"/arguments.version/"esp32s3"/name
    ensure_backend(f"https://github.com/awawa-dev/Hyperk-Backend/releases/download/{arguments.version}/{name}", library, checksum)
    extract_ui(library, arguments.output)
    print("Verified backend GPIO/UI contract and extracted browser assets for integration tests.")

if __name__ == "__main__": main()
