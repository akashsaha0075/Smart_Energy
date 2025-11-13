import json
from pathlib import Path

DEVICES_JSON_PATH = Path("devices.json")

def load_devices():
    if not DEVICES_JSON_PATH.exists():
        return []
    try:
        return json.loads(DEVICES_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_devices(devs: list):
    DEVICES_JSON_PATH.write_text(json.dumps(devs, indent=4), encoding="utf-8")
