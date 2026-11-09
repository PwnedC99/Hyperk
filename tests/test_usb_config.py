"""Check USB flags after PlatformIO resolves the real environment inheritance."""
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("platformio"), "PlatformIO is required")
class UsbConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [sys.executable, "-m", "platformio", "project", "config", "--json-output"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        cls.config = {name: dict(options) for name, options in json.loads(result.stdout)}

    def tokens(self, section, option="build_flags"):
        value = self.config[section].get(option, [])
        return shlex.split(" ".join(value) if isinstance(value, list) else value)

    def test_cdc_section_and_references(self):
        self.assertIn("env:esp32-enable-cdc", self.config)
        self.assertNotIn("end:esp32-enable-cdc", self.config)
        text = (ROOT / "platformio.ini").read_text()
        for section in re.findall(r"\$\{([^}]+)\.build_flags\}", text):
            self.assertIn(section, self.config)
        self.assertNotIn("${end:esp32-enable-cdc.build_flags}", text)

    def test_usb_flags_survive_inheritance(self):
        for name in ["esp32s3", "esp32s3-fh4r2", "esp32s3-fh4r2-diagnostic", "esp32s2", "esp32c3", "esp32c5", "esp32c6"]:
            with self.subTest(environment=name):
                section = "env:" + name
                flags = self.tokens(section)
                self.assertEqual([flag for flag in flags if flag.startswith("-DARDUINO_USB_CDC_ON_BOOT")],
                                 ["-DARDUINO_USB_CDC_ON_BOOT=1"])
                self.assertEqual([flag for flag in flags if flag.startswith("-DARDUINO_USB_MODE")],
                                 ["-DARDUINO_USB_MODE=1"])
                unflags = self.tokens(section, "build_unflags")
                self.assertNotIn("-DARDUINO_USB_CDC_ON_BOOT=1", unflags)
                if name == "esp32s2":
                    self.assertIn("-DARDUINO_USB_MODE=1", unflags)
                else:
                    self.assertNotIn("-DARDUINO_USB_MODE=1", unflags)
                self.assertNotIn("-DSERIAL_PORT_LITE", flags)
                self.assertNotIn("-DENABLE_DEBUG", flags)

    def test_custom_board_settings_are_retained(self):
        custom = self.config["env:esp32s3-fh4r2"]
        self.assertEqual(custom["extends"], ["env:esp32s3"])
        self.assertEqual(custom["board"], "esp32-s3-devkitc-1")
        self.assertEqual(custom["board_upload.flash_size"], "4MB")
        self.assertEqual(custom["board_build.partitions"], "partitions_4mb.csv")
        self.assertEqual(custom["custom_backend_env"], "esp32s3")
        flags = self.tokens("env:esp32s3-fh4r2")
        for flag in ["-DHYPERK_S3_EXTRA_GPIOS", "-DHYPERK_BOARD_UI", "-DHYPERK_WIFI_RECOVERY",
                     "-DPERIPHERAL_ENABLE_GPIO=1", "-DUSE_MULTI_ESP32_LED_STRIP",
                     "-Wl,--wrap=_ZN14AsyncWebServer5beginEv"]:
            self.assertIn(flag, flags)

    def test_http_stack_and_diagnostic_separation(self):
        for name in ["esp32s3-fh4r2", "esp32s3-fh4r2-diagnostic"]:
            flags = self.tokens("env:" + name)
            self.assertEqual([f for f in flags if f.startswith("-DCONFIG_ASYNC_TCP_STACK_SIZE=")],
                             ["-DCONFIG_ASYNC_TCP_STACK_SIZE=16384"])
            self.assertEqual("-DHYPERK_CONFIG_DIAGNOSTICS" in flags, name.endswith("-diagnostic"))


if __name__ == "__main__":
    unittest.main()
