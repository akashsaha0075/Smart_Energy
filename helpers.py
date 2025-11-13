import json
import os
import streamlit as st
from datetime import datetime, timedelta, timezone

dhaka_tz = timezone(timedelta(hours=6))


def parse_metrics(status_json: dict):
    result = status_json.get("result", [])
    m = {x.get("code"): x.get("value") for x in result}
    voltage = (m.get("cur_voltage") or 0) / 10.0     # deciV → V
    power   = (m.get("cur_power") or 0) * 1.0        # W
    current = (m.get("cur_current") or 0) / 1000.0   # mA → A
    # integrate power over 5s: kWh = W * (5/3600) / 1000
    energy_kwh = power * (5.0 / 3600.0) / 1000.0
    return voltage, current, power, energy_kwh

def build_doc(device_id: str, device_name: str, v: float, c: float, p: float, e: float):
    return {
        "timestamp": datetime.now(dhaka_tz),
        "device_id": device_id,
        "device_name": device_name or "",
        "voltage": v,
        "current": c,
        "power": p,
        "energy_kWh": e,
    }


DEVICE_FILE = "devices.json"

def load_devices():
    """Load all devices from the JSON file."""
    if not os.path.exists(DEVICE_FILE):
        return []
    with open(DEVICE_FILE, "r") as f:
        return json.load(f)

def save_devices(devices):
    """Save all devices to the JSON file."""
    with open(DEVICE_FILE, "w") as f:
        json.dump(devices, f, indent=4)

def go_home():
    """Navigate back to home page."""
    st.session_state.page = "home"

