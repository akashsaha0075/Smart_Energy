
import os
import json
import time
import hmac
import hashlib
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---- Third-party ----
import streamlit as st
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

# ==============================
# 📦 ENV & CONSTANTS
# ==============================
load_dotenv()
ACCESS_ID = os.getenv("TUYA_ACCESS_ID", "")
ACCESS_SECRET = os.getenv("TUYA_ACCESS_SECRET", "")
API_ENDPOINT = os.getenv("TUYA_API_ENDPOINT", "https://openapi.tuyaeu.com")

MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "tuya_energy")

DATA_DIR = Path("data")
DEVICES_JSON_PATH = Path("devices.json")
HTTP_TIMEOUT = 15  # seconds

# Electricity slab rates (Bangladesh, example)
RATES = [
    (50, 4.63), (75, 5.26), (200, 7.20), (300, 7.59),
    (400, 8.02), (600, 12.67), (float("inf"), 14.61)
]

# ==============================
# 🔐 TUYA SIGNING & API
# ==============================
def _make_sign(client_id, secret, method, url, access_token: str = "", body: str = ""):
    t = str(int(time.time() * 1000))
    message = client_id + access_token + t
    string_to_sign = "\n".join([
        method.upper(),
        hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "",
        url
    ])
    sign_str = message + string_to_sign
    sign = hmac.new(secret.encode("utf-8"), sign_str.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    return sign, t

@st.cache_data(show_spinner=False, ttl=60)
def get_token():
    """Cache the token for 60s to reduce calls."""
    path = "/v1.0/token?grant_type=1"
    sign, t = _make_sign(ACCESS_ID, ACCESS_SECRET, "GET", path)
    headers = {
        "client_id": ACCESS_ID,
        "sign": sign,
        "t": t,
        "sign_method": "HMAC-SHA256"
    }
    res = requests.get(API_ENDPOINT + path, headers=headers, timeout=HTTP_TIMEOUT)
    data = res.json()
    if not data.get("success"):
        raise RuntimeError(f"Failed to get token: {data}")
    return data["result"]["access_token"]

def get_device_status(device_id: str, token: str):
    path = f"/v1.0/devices/{device_id}/status"
    sign, t = _make_sign(ACCESS_ID, ACCESS_SECRET, "GET", path, token)
    headers = {
        "client_id": ACCESS_ID, "sign": sign, "t": t,
        "access_token": token, "sign_method": "HMAC-SHA256"
    }
    res = requests.get(API_ENDPOINT + path, headers=headers, timeout=HTTP_TIMEOUT)
    return res.json()

def control_device(device_id: str, token: str, command: str, value):
    path = f"/v1.0/devices/{device_id}/commands"
    body = json.dumps({"commands": [{"code": command, "value": value}]})
    sign, t = _make_sign(ACCESS_ID, ACCESS_SECRET, "POST", path, token, body)
    headers = {
        "client_id": ACCESS_ID, "sign": sign, "t": t,
        "access_token": token, "sign_method": "HMAC-SHA256",
        "Content-Type": "application/json"
    }
    res = requests.post(API_ENDPOINT + path, headers=headers, data=body, timeout=HTTP_TIMEOUT)
    return res.json()

# ==============================
# 🗄️ MONGO HELPERS
# ==============================
@st.cache_resource(show_spinner=False)
def _get_mongo():
    if not MONGODB_URI:
        return None
    return MongoClient(MONGODB_URI, tls=True)

def _get_db(client: MongoClient):
    db = None
    try:
        db = client.get_default_database()
    except Exception:
        db = None
    if db is None:
        db = client[MONGODB_DB]
    return db

def _get_collection(device_id: str):
    client = _get_mongo()
    if client is None:
        return None
    coll = _get_db(client)[f"readings_{device_id}"]
    try:
        coll.create_index([("timestamp", ASCENDING)])
    except Exception:
        pass
    return coll

# ==============================
# 📊 LOGGING
# ==============================
def _parse_metrics(status_json: dict):
    result = status_json.get("result", [])
    metrics = {item.get("code"): item.get("value") for item in result}
    voltage = (metrics.get("cur_voltage") or 0) / 10.0       # deciVolts -> V
    power = metrics.get("cur_power") or 0                    # W
    current = (metrics.get("cur_current") or 0) / 1000.0     # mA -> A
    energy_kWh = power / 1000.0 / 720.0 * 60.0               # adjust for 5s logging (~ 5s / hr) -> kWh
    # Explanation: For 5-second interval, power (W) * (5/3600) h = W * 0.001388.. kWh
    # Using simplified computation below for precision:
    energy_kWh = power * (5.0 / 3600.0) / 1000.0
    return voltage, current, power, energy_kWh

def log_data(device_id: str, status_data: dict, device_name: str | None = None):
    voltage, current, power, energy_kWh = _parse_metrics(status_data)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DATA_DIR / f"{device_id}.csv"

    ts_dt = datetime.now(timezone.utc)
    ts_str = ts_dt.strftime("%Y-%m-%d %H:%M:%S")

    row = {
        "timestamp": ts_str,
        "device_id": device_id,
        "device_name": device_name or "",
        "voltage": voltage,
        "current": current,
        "power": power,
        "energy_kWh": energy_kWh,
    }

    # CSV
    df = pd.DataFrame([row])
    write_header = not file_path.exists()
    df.to_csv(file_path, mode="a", header=write_header, index=False)

    # Mongo
    coll = _get_collection(device_id)
    if coll is not None:
        try:
            coll.insert_one({
                **row,
                "timestamp": ts_dt,   # store as datetime in Mongo
            })
        except PyMongoError as e:
            print(f"Mongo insert error: {e}")

    return row

# ==============================
# 💸 BILLING
# ==============================
def calculate_tiered_cost(units_kwh: float) -> float:
    remaining = units_kwh
    last_upper = 0
    cost = 0.0
    for upper, rate in RATES:
        if remaining <= 0:
            break
        slab_units = min(remaining, upper - last_upper)
        cost += slab_units * rate
        remaining -= slab_units
        last_upper = upper
    return round(cost, 2)

def daily_and_monthly_bill(device_id: str):
    path = DATA_DIR / f"{device_id}.csv"
    if not path.exists():
        return 0, 0, 0, 0
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df["date"] = df["timestamp"].dt.date
    today = datetime.now().date()
    daily_df = df[df["date"] == today]
    daily_units = round(daily_df["energy_kWh"].sum(), 3)
    daily_cost = calculate_tiered_cost(daily_units)
    month_df = df[df["timestamp"].dt.month == datetime.now().month]
    monthly_units = round(month_df["energy_kWh"].sum(), 3)
    monthly_cost = calculate_tiered_cost(monthly_units)
    return daily_units, daily_cost, monthly_units, monthly_cost

# ==============================
# 📁 DEVICES JSON
# ==============================
def load_devices():
    if not DEVICES_JSON_PATH.exists():
        return []
    try:
        return json.loads(DEVICES_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_devices(devs: list):
    DEVICES_JSON_PATH.write_text(json.dumps(devs, indent=4), encoding="utf-8")

# ==============================
# 🖥️ STREAMLIT UI
# ==============================
st.set_page_config(page_title="Smart Plug Dashboard", layout="wide")

if "page" not in st.session_state:
    st.session_state.page = "home"
if "current_device" not in st.session_state:
    st.session_state.current_device = None

def go_home():
    st.session_state.page = "home"

def go_device_detail(device_id):
    st.session_state.page = "device_detail"
    st.session_state.current_device = device_id

# ---- Sidebar ----
with st.sidebar:
    st.header("Navigation")
    page_choice = st.radio("Go to", ["Home", "Add Device", "Manage Devices"], index=0)
    if page_choice == "Home":
        st.session_state.page = "home"
    elif page_choice == "Add Device":
        st.session_state.page = "add_device"
    elif page_choice == "Manage Devices":
        st.session_state.page = "manage_devices"

    st.markdown("---")
    st.caption("Env")
    st.code(f"TUYA_API_ENDPOINT={API_ENDPOINT}")
    if MONGODB_URI:
        st.success("MongoDB: configured")
    else:
        st.warning("MongoDB: not configured")

# ---- Pages ----
def home_page():
    st.title("💡 Smart Plug Dashboard")
    st.markdown("Monitor and manage your smart devices easily.")
    devices = load_devices()
    if not devices:
        st.info("No devices added yet. Use **Add Device**.")
        return
    cols = st.columns(3)
    for i, d in enumerate(devices):
        with cols[i % 3]:
            st.subheader(f"🔌 {d['name']}")
            st.text(f"ID: {d['id']}")
            if st.button(f"View {d['name']}", key=f"v_{i}"):
                go_device_detail(d["id"])

def add_device_page():
    st.header("➕ Add New Device")
    name = st.text_input("Device Name")
    dev_id = st.text_input("Device ID")
    if st.button("Save Device"):
        if name and dev_id:
            devs = load_devices()
            devs.append({"name": name, "id": dev_id})
            save_devices(devs)
            st.success(f"Added {name}")
        else:
            st.warning("Please enter both name and ID.")

def manage_devices_page():
    st.header("⚙️ Manage Devices")
    devs = load_devices()
    if not devs:
        st.info("No devices to manage.")
        return
    for i, d in enumerate(devs):
        col1, col2, col3 = st.columns([3, 3, 1])
        with col1:
            new_name = st.text_input("Name", value=d["name"], key=f"nm_{i}")
        with col2:
            new_id = st.text_input("ID", value=d["id"], key=f"id_{i}")
        with col3:
            if st.button("Save", key=f"sv_{i}"):
                devs[i] = {"name": new_name, "id": new_id}
                save_devices(devs)
                st.success("Saved")
            if st.button("Delete", key=f"dl_{i}"):
                del devs[i]
                save_devices(devs)
                st.warning("Deleted")
                st.experimental_rerun()

def device_detail_page():
    devs = load_devices()
    device_id = st.session_state.get("current_device")
    device = next((x for x in devs if x["id"] == device_id), None)
    if not device:
        st.error("Device not found")
        return

    st.title(f"🔌 {device['name']} — Live Dashboard")
    # Auto-refresh every 5 seconds
    st_autorefresh = st.experimental_rerun  # fallback alias if st_autorefresh not available
    try:
        st_autorefresh = st.experimental_memo  # dummy to avoid linter
    except Exception:
        pass
    st_autorefresh = st.autorefresh if hasattr(st, "autorefresh") else None
    if st_autorefresh:
        st_autorefresh(interval=5000, key="auto5s")

    # Fetch + Log on each render
    try:
        token = get_token()
        response = get_device_status(device_id, token)
        if response.get("success"):
            entry = log_data(device_id, response, device_name=device["name"])
        else:
            st.error(f"Tuya error: {response}")
    except Exception as e:
        st.error(f"Fetch/log error: {e}")
        entry = None

    # Parse latest
    latest_voltage = latest_power = latest_current = 0.0
    if entry:
        latest_voltage = entry["voltage"]
        latest_power = entry["power"]
        latest_current = entry["current"]

    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("🔋 Voltage (V)", f"{latest_voltage:.1f}")
    m2.metric("⚡ Power (W)", f"{latest_power:.1f}")
    m3.metric("🔌 Current (A)", f"{latest_current:.3f}")

    # Control
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Turn ON"):
            try:
                token = get_token()
                res = control_device(device_id, token, "switch_1", True)
                st.info(res)
            except Exception as e:
                st.error(e)
    with c2:
        if st.button("Turn OFF"):
            try:
                token = get_token()
                res = control_device(device_id, token, "switch_1", False)
                st.info(res)
            except Exception as e:
                st.error(e)

    # Recent trend (CSV)
    st.markdown("### 📈 Recent Power (last 100 samples)")
    path = DATA_DIR / f"{device_id}.csv"
    if path.exists():
        df_recent = pd.read_csv(path).tail(100)
        st.line_chart(df_recent.set_index("timestamp")["power"])
    else:
        st.info("No data yet.")

    # Billing
    st.markdown("### 💰 Electricity Bill Estimate")
    d_units, d_cost, m_units, m_cost = daily_and_monthly_bill(device_id)
    b1, b2 = st.columns(2)
    with b1:
        st.metric("📅 Today's Consumption", f"{d_units:.3f} kWh")
        st.metric("💸 Today's Bill", f"{d_cost:.2f} ৳")
    with b2:
        st.metric("🗓 Monthly Consumption", f"{m_units:.3f} kWh")
        st.metric("💰 Monthly Bill", f"{m_cost:.2f} ৳")

    # Historical range (CSV first; can extend to Mongo query if wanted)
    st.markdown("### 🕰️ Historical Data")
    colA, colB, colC = st.columns(3)
    with colA:
        start_date = st.date_input("Start date", value=datetime.now().date() - timedelta(days=1))
    with colB:
        end_date = st.date_input("End date", value=datetime.now().date())
    with colC:
        resample = st.selectbox("Aggregation", ["raw (no aggregation)", "1-min avg", "5-min avg", "15-min avg"], index=1)

    if path.exists():
        df = pd.read_csv(path, parse_dates=["timestamp"])
        # Filter range (inclusive)
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        dff = df[(df["timestamp"] >= pd.Timestamp(start_dt)) & (df["timestamp"] <= pd.Timestamp(end_dt))].copy()
        if not dff.empty:
            dff = dff.set_index("timestamp").sort_index()
            if resample != "raw (no aggregation)":
                rule = {"1-min avg": "1T", "5-min avg": "5T", "15-min avg": "15T"}[resample]
                dff = dff.resample(rule).mean(numeric_only=True).dropna()
            st.line_chart(dff[["power"]])
            st.dataframe(dff.reset_index().tail(200))
        else:
            st.info("No data in the selected range.")

    with st.expander("📜 Raw Tuya Response"):
        st.json(response if 'response' in locals() else {})

# Router
page = st.session_state.page
if page == "home":
    home_page()
elif page == "add_device":
    add_device_page()
elif page == "manage_devices":
    manage_devices_page()
elif page == "device_detail":
    device_detail_page()
