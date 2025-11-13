import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import streamlit as st

from devices import load_devices, save_devices
from get_power_data import fetch_and_log_once
from tuya_api import control_device, get_token
from billing import daily_monthly_for

from devices import load_devices, save_devices
from get_power_data import fetch_and_log_once
from tuya_api import control_device, get_token
from billing import daily_monthly_for
from tuya_api_mongo import latest_docs, range_docs
from streamlit_autorefresh import st_autorefresh
from helpers import go_home, load_devices, save_devices







# # in app.py (top-level, after imports)
# import threading, time
# from devices import load_devices
# from get_power_data import fetch_and_log_once

# if "collector_started" not in st.session_state:
#     st.session_state.collector_started = False

# def _collector(stop_event, interval=30.0):
#     devices = load_devices()
#     while not stop_event.is_set():
#         for d in devices:
#             try:
#                 fetch_and_log_once(d["id"], d.get("name",""))
#             except Exception:
#                 pass
#         stop_event.wait(interval)

# if not st.session_state.collector_started:
#     st.session_state.collector_stop = threading.Event()
#     t = threading.Thread(target=_collector, args=(st.session_state.collector_stop, 5.0), daemon=True)
#     t.start()
#     st.session_state.collector_started = True

# # (Optional) add a stop button in sidebar
# if st.sidebar.button("Stop background fetcher"):
#     st.session_state.collector_stop.set()



DATA_DIR = Path("data")

st.set_page_config(page_title="Smart Energy Dashboard", layout="wide")

# Sidebar nav
page = st.sidebar.radio("Navigate", ["Home", "Add Device", "Manage Devices"], index=0)
st.sidebar.markdown("---")
st.sidebar.caption("Auto-logging every 5s while a device page is open.")

def home():
    st.title("💡 Smart Energy Dashboard")
    devs = load_devices()
    if not devs:
        st.info("No devices yet. Go to **Add Device**.")
        return
    cols = st.columns(3)
    for i, d in enumerate(devs):
        with cols[i % 3]:
            st.subheader(f"🔌 {d['name']}")
            st.text(f"ID: {d['id']}")
            if st.button(f"Open {d['name']}", key=f"open_{i}"):
                st.session_state["page"] = "device"
                st.session_state["device_id"] = d["id"]
                st.session_state["device_name"] = d["name"]



def add_device():
    st.header("➕ Add Device")
    name = st.text_input("Device Name")
    dev_id = st.text_input("Device ID")
    if st.button("Save"):
        if name and dev_id:
            devs = load_devices()
            devs.append({"name": name, "id": dev_id})
            save_devices(devs)
            st.success("Device added.")
        else:
            st.warning("Enter both name and ID.")

def manage_devices():
    st.header("⚙️ Manage Devices")
    devs = load_devices()
    if not devs:
        st.info("No devices to manage.")
        return
    for i, d in enumerate(devs):
        c1, c2, c3 = st.columns([3, 3, 1])
        with c1:
            new_name = st.text_input("Name", value=d["name"], key=f"nm_{i}")
        with c2:
            new_id = st.text_input("ID", value=d["id"], key=f"id_{i}")
        with c3:
            if st.button("Save", key=f"sv_{i}"):
                devs[i] = {"name": new_name, "id": new_id}
                save_devices(devs)
                st.success("Saved.")
            if st.button("Delete", key=f"dl_{i}"):
                del devs[i]
                save_devices(devs)
                st.warning("Deleted.")
                st.experimental_rerun()


# --- Robust CSV reader ---
def read_csv_safe(path):
    # required columns in your schema
    required = ["timestamp", "device_id", "device_name", "voltage", "current", "power", "energy_kWh"]
    try:
        df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    except TypeError:
        # for older pandas (<1.3) which doesn't have on_bad_lines
        df = pd.read_csv(path, engine="python", error_bad_lines=False, warn_bad_lines=True)

    # keep only known columns if present, ignore stray columns
    cols = [c for c in required if c in df.columns]
    if cols:
        df = df[cols]
    # ensure timestamp is datetime
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df

#---------------------------------------------------------------------------------

def go_device_detail(device_id):
    st.session_state.page = "device_detail"
    st.session_state.current_device = device_id


# ---- HOME PAGE ----
def home_page():
    st.title("💡 Smart Plug Dashboard")
    st.markdown("### Monitor and manage your smart devices easily")

    # Buttons row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("📘 User Manual"):
            st.session_state.page = "user_manual"
    with col2:
        st.write("")  # spacing
        st.markdown("### ⚡ My Devices")
    with col3:
        if st.button("➕ Add Device"):
            st.session_state.page = "add_device"
    with col4:
        if st.button("⚙️ Manage Devices"):
            st.session_state.page = "manage_devices"

    st.markdown("---")

    devices = load_devices()
    if not devices:
        st.info("No devices added yet. Click **Add Device** to get started.")
        return

    # Device cards grid
    cols = st.columns(3)
    for i, device in enumerate(devices):
        col = cols[i % 3]
        with col:
            st.container()
            st.markdown(f"#### 🔌 {device['name']}")
            st.markdown(f"**Device ID:** `{device['id']}`")
            if st.button(f"View Details ({device['name']})", key=f"view_{i}"):
                go_device_detail(device["id"])
            st.markdown("---")

#-------------------------------------------------------------------------------------









def device_page():
    dev_id = st.session_state.get("device_id", "")
    dev_name = st.session_state.get("device_name", "")
    if not dev_id:
        st.error("No device selected.")
        return
    
    # Rerun the script every 5s
    st_autorefresh(interval=5000, key=f"data_refresh_{dev_id}")

    st.title(f"🔌 {dev_name} — Live")
    # auto-refresh every 5s
    # auto-refresh every 5s (supported in Streamlit ≥1.24)
    try:
        st.autorefresh(interval=5000, key=f"auto_{dev_id}")
    except AttributeError:
        # fallback if autorefresh not available
        pass


    # fetch + log (CSV + Mongo)
    result = fetch_and_log_once(dev_id, dev_name)
    if "error" in result:
        st.error(f"Tuya API error: {result['error']}")
    row = result.get("row", {})
    v = row.get("voltage", 0.0)
    c = row.get("current", 0.0)
    p = row.get("power", 0.0)

    m1, m2, m3 = st.columns(3)
    m1.metric("🔋 Voltage (V)", f"{v:.1f}")
    m2.metric("⚡ Power (W)", f"{p:.1f}")
    m3.metric("🔌 Current (A)", f"{c:.3f}")

    # controls
    colA, colB = st.columns(2)
    with colA:
        if st.button("Turn ON"):
            try:
                token = get_token()
                st.info(control_device(dev_id, token, "switch_1", True))
            except Exception as e:
                st.error(e)
    with colB:
        if st.button("Turn OFF"):
            try:
                token = get_token()
                st.info(control_device(dev_id, token, "switch_1", False))
            except Exception as e:
                st.error(e)

    # recent trend
    st.markdown("### 📈 Recent Power (last 100 samples)")
    df_recent = latest_docs(dev_id, n=30)
    if not df_recent.empty:
        st.line_chart(df_recent.set_index("timestamp")["power"])
    else:
        st.info("No data yet.")


    # billing
    st.markdown("### 💰 Bill Estimate")
    d_units, d_cost, m_units, m_cost = daily_monthly_for(dev_id)
    b1, b2 = st.columns(2)
    with b1:
        st.metric("📅 Today kWh", f"{d_units:.3f}")
        st.metric("💸 Today BDT", f"{d_cost:.2f}")
    with b2:
        st.metric("🗓 Month kWh", f"{m_units:.3f}")
        st.metric("💰 Month BDT", f"{m_cost:.2f}")



    # historical
    st.markdown("### 🕰️ Historical Data")
    c1, c2, c3 = st.columns(3)
    with c1:
        start_date = st.date_input("Start", value=datetime.now().date() - timedelta(days=1))
    with c2:
        end_date = st.date_input("End", value=datetime.now().date())
    with c3:
        agg = st.selectbox("Aggregation", ["raw", "1-min", "5-min", "15-min"], index=1)

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt   = datetime.combine(end_date, datetime.max.time())
    df = range_docs(dev_id, start_dt, end_dt)

    if not df.empty:
        df = df.sort_values("timestamp").set_index("timestamp")
        if agg != "raw":
            rule = {"1-min": "1T", "5-min": "5T", "15-min": "15T"}[agg]
            df = df.resample(rule).mean(numeric_only=True).dropna()
        st.line_chart(df[["power"]])
        st.dataframe(df.reset_index().tail(200))
    else:
        st.info("No data in selected range.")



# router
if "page" in st.session_state and st.session_state["page"] == "Home":
    home_page()      
    # device_page()
else:
    if page == "Home":
        home_page()
    elif page == "Add Device":
        add_device()
    elif page == "Manage Devices":
        manage_devices()
    elif page == "device_detail":
        device_page()




# # ---- ROUTER ----
# page = st.session_state.page
# if page == "home":
#     home_page()
# elif page == "user_manual":
#     user_manual_page()
# elif page == "add_device":
#     add_device_page()
# elif page == "manage_devices":
#     manage_devices_page()
# elif page == "device_detail":
#     device_detail_page()



# # router
# if "page" in st.session_state and st.session_state["page"] == "device":
#     device_page()
# else:
#     if page == "Home":
#         go_home()
#     elif page == "Add Device":
#         add_device()
#     elif page == "Manage Devices":
#         manage_devices()


