"""Read public settings for a before/after comparison without changing the ESP."""
import argparse
import json
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.4.1")
    parser.add_argument("--expected-ssid")
    args = parser.parse_args()

    def get(path):
        with urlopen(f"http://{args.host}{path}", timeout=10) as response:
            return json.load(response)

    board = get("/api/board")
    config = get("/api/get_current_config")["config"]
    public = {
        "build_id": board.get("build_id"),
        "reset_reason": board.get("reset_reason"),
        "uptime_ms": board.get("uptime_ms"),
        "storage": board.get("storage"),
        "wifi_connected": board.get("wifi", {}).get("connected"),
        "wifi_disconnect_reason": board.get("wifi", {}).get("last_disconnect_reason"),
        "wifi_credentials_present": bool(config.get("ssid")),
        "wifi_ssid_matches": config.get("ssid") == args.expected_ssid if args.expected_ssid is not None else None,
        "deviceName": config.get("deviceName"),
        "led": {key: config.get(key) for key in ["type", "numLeds", "brightness", "r", "g", "b", "effect"]},
        "segments": config.get("segments"),
        "quirks": {key: config.get(key) for key in ["disableSpiEmulation", "min-segments-for-i2s"]},
    }
    print(json.dumps(public, indent=2))


if __name__ == "__main__":
    main()
