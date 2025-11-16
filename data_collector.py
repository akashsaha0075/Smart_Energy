"""
data_collector.py
-----------------
Headless data collector for Tuya smart socket metrics.

- Reads devices from devices.json (via helpers.load_devices)
- Periodically calls fetch_and_log_once(...) for each device
- fetch_and_log_once() will insert readings into MongoDB using tuya_api_mongo

Requirements:
- Same virtualenv / dependencies as your Streamlit app
- Environment variables (or .env) set for:
    TUYA_ACCESS_ID
    TUYA_ACCESS_SECRET
    TUYA_API_ENDPOINT
    MONGODB_URI
    MONGODB_DB
"""

import time
from datetime import datetime

from helpers import load_devices
from get_power_data import fetch_and_log_once
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # built-in in Python 3.9+

DHAKA_TZ = ZoneInfo("Asia/Dhaka")


# How often to log data (seconds)
INTERVAL_SECONDS = 10  # change this if you want slower/faster collection


def main():
    devices = load_devices()
    if not devices:
        print("[collector] No devices found in devices.json. Exiting.")
        return

    print(f"[collector] Starting data collector for {len(devices)} device(s).")
    print(f"[collector] Collection interval: {INTERVAL_SECONDS} seconds.")
    print("[collector] Press Ctrl+C to stop.\n")

    try:
        while True:
            loop_start_utc = datetime.now(timezone.utc)
            loop_start_local = loop_start_utc.astimezone(DHAKA_TZ)
            print(f"[collector] ==== New cycle at {loop_start_local.isoformat(timespec='seconds')} ====")


            # Reload devices each cycle (optional: comment out if you don't want dynamic changes)
            devices = load_devices()

            for d in devices:
                dev_id = d.get("id")
                dev_name = d.get("name", "")

                if not dev_id:
                    print("[collector] Skipping device with missing 'id' field:", d)
                    continue

                try:
                    result = fetch_and_log_once(dev_id, dev_name)
                    now_local = datetime.now(timezone.utc).astimezone(DHAKA_TZ)
                    print(
                        f"[collector] {now_local.isoformat(timespec='seconds')} | "
                        f"{dev_name or dev_id} -> {result}"
                    )
                except Exception as e:
                    now_local = datetime.now(timezone.utc).astimezone(DHAKA_TZ)
                    print(
                        f"[collector] ERROR at {now_local.isoformat(timespec='seconds')} "
                        f"for device {dev_name or dev_id}: {e}"
                    )

            # Sleep until next cycle
            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[collector] Stopped by user (Ctrl+C). Goodbye.")


if __name__ == "__main__":
    main()
