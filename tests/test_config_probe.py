"""Validate the read-only probe against the backend's flat API envelope."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ProbeTests(unittest.TestCase):
    def test_public_api_shape_and_no_credentials(self):
        spec = importlib.util.spec_from_file_location("config_probe", ROOT / "diagnostics/config-persistence/probe.py")
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        config = {"config": {"ssid": "example-network", "pass": "example-secret", "numLeds": 258,
                             "brightness": 254, "disableSpiEmulation": False,
                             "segments": [{"startIndex": 0, "data": 37}, {"startIndex": 129, "data": 38}]}}
        board = {"storage": {"config_valid": True}, "wifi": {"connected": False}, "build_id": "test"}
        responses = [io.BytesIO(json.dumps(item).encode()) for item in [board, config]]
        output = io.StringIO()
        with patch.object(probe, "urlopen", side_effect=responses) as request, \
                patch("sys.argv", ["probe.py", "--expected-ssid", "example-network"]), contextlib.redirect_stdout(output):
            probe.main()
        public = json.loads(output.getvalue())
        self.assertEqual(public["led"]["numLeds"], 258)
        self.assertEqual(public["led"]["brightness"], 254)
        self.assertEqual(public["segments"][1]["data"], 38)
        self.assertTrue(public["wifi_ssid_matches"])
        self.assertNotIn("example-network", output.getvalue())
        self.assertNotIn("example-secret", output.getvalue())
        self.assertEqual([call.args[0] for call in request.call_args_list],
                         ["http://192.168.4.1/api/board", "http://192.168.4.1/api/get_current_config"])


if __name__ == "__main__":
    unittest.main()
