"""Capture diagnostic USB output without sending firmware or reset commands."""
import argparse
from pathlib import Path
import time

import serial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--output", type=Path, default=Path(".pio/config-investigation/usb.log"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.seconds
    print(f"Reading {args.port}; no data or reset commands are sent. Ctrl+C stops capture.")
    with args.output.open("ab") as log:
        while time.monotonic() < deadline:
            port = serial.Serial(port=None, baudrate=115200, timeout=0.2)
            port.dtr = False
            port.rts = False
            port.port = args.port
            try:
                port.open()
                while time.monotonic() < deadline:
                    data = port.read(4096)
                    if data:
                        log.write(data)
                        log.flush()
                        print(data.decode("utf-8", errors="replace"), end="", flush=True)
            except (serial.SerialException, OSError) as error:
                print(f"\nUSB unavailable: {error}; retrying in one second.")
                time.sleep(1)
            finally:
                port.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCapture stopped.")
