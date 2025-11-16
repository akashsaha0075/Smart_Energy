# =========================================================
# app.py — Dark Dashboard (Sky Blue + Neon Cards + User Manual)
# Streamlit >= 1.36
# =========================================================

from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go
import plotly.express as px

# --- Project Modules ---
from devices import load_devices, save_devices
from get_power_data import fetch_and_log_once
from tuya_api import control_device, get_token
from tuya_api_mongo import latest_docs, range_docs
from billing import (
    daily_monthly_for,
    aggregate_totals_all_devices
)

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------
st.set_page_config(
    page_title="Smart Plug — Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------------------------------------------------------
# DARK THEME + SKY BLUE BUTTONS
# ---------------------------------------------------------
st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
  background: linear-gradient(180deg, #071025 0%, #0b1020 100%);
  color: #e6eef6;
}
[data-testid="stHeader"] { background: transparent; }

.app-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 26px; border-radius: 10px;
  background: rgba(255,255,255,0.03);
  box-shadow: 0 6px 16px rgba(0,0,0,0.45);
  margin-bottom: 20px;
}
.brand { display:flex; align-items:center; gap:10px; }
.brand .title { font-size:18px; font-weight:700; color:#fff; }

.card {
  background: rgba(255,255,255,0.04);
  border-radius: 10px;
  padding: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  margin-bottom: 16px;
}
.metric-label { color: #aaa; font-size: 13px; }
.metric-value { font-size: 20px; font-weight: 700; color: #fff; }

/* Sky-blue buttons */
.stButton>button {
  background: linear-gradient(90deg, #00c2ff, #0090ff);
  color: #fff !important;
  font-weight: 700;
  border: none;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,194,255,0.25);
  transition: all .2s ease;
}
.stButton>button:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 20px rgba(0,194,255,0.45);
}

/* Footer */
.footer {
  text-align: center;
  padding: 16px;
  font-size: 13px;
  color: #00c2ff;
  opacity: 0.8;
  margin-top: 40px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------
if "route" not in st.session_state:
    st.session_state.route = "home"
if "current_device_id" not in st.session_state:
    st.session_state.current_device_id = None
if "current_device_name" not in st.session_state:
    st.session_state.current_device_name = None


def set_route(r):
    st.session_state.route = r


def go_home():
    set_route("home")


def go_mydevices():
    set_route("mydevices")


def go_add():
    set_route("add")


def go_manage():
    set_route("manage")


def go_manual():
    set_route("manual")


def go_device_detail(i, n):
    st.session_state.current_device_id = i
    st.session_state.current_device_name = n
    set_route("device")

# ---------------------------------------------------------
# TOP NAV BAR
# ---------------------------------------------------------
def render_topbar():
    st.markdown("""
        <h1 style='text-align:center;font-family:Poppins,sans-serif;
        font-weight:700;font-size:2.8em;color:white;'>
        🌱 Green Power Monitor</h1><br><br>
    """, unsafe_allow_html=True)

    n1, n2, n3, n4, n5 = st.columns([1, 1, 1, 1, 1])
    with n1:
        if st.button("🏠 Dashboard"):
            go_home()
            st.rerun()
    with n2:
        if st.button("⚡ My Devices"):
            go_mydevices()
            st.rerun()
    with n3:
        if st.button("➕ Add"):
            go_add()
            st.rerun()
    with n4:
        if st.button("⚙️ Manage"):
            go_manage()
            st.rerun()
    with n5:
        if st.button("📘 User Manual"):
            go_manual()
            st.rerun()


render_topbar()

# ---------------------------------------------------------
# PAGE: HOME
# ---------------------------------------------------------
def page_home():
    st.title("📊 Overview")

    devices = load_devices()
    total_devices = len(devices)
    p_now, v_now, t_kwh, t_bdt, m_kwh, m_bdt = aggregate_totals_all_devices(devices)

    cols = st.columns(5)
    data = [
        ("Devices", total_devices),
        ("Power (W)", f"{p_now/10:.1f}"),
        ("Voltage (V)", f"{v_now:.1f}"),
        ("Today (BDT)", f"{t_bdt:.2f}"),
        ("Month (BDT)", f"{m_bdt:.2f}")
    ]
    for c, (lbl, val) in zip(cols, data):
        with c:
            st.markdown(
                f'<div class="card"><div class="metric-label">{lbl}</div>'
                f'<div class="metric-value">{val}</div></div>',
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------
# PAGE: MY DEVICES
# ---------------------------------------------------------
def page_mydevices():
    st.title("⚡ My Devices")
    devs = load_devices()
    if not devs:
        st.info("No devices.")
        if st.button("➕ Add Device"):
            go_add()
            st.rerun()
        return

    cols = st.columns(3)
    for i, d in enumerate(devs):
        with cols[i % 3]:
            st.markdown(
                f'<div class="card"><b>{d["name"]}</b><br>'
                f'<span class="metric-label">{d["id"]}</span></div>',
                unsafe_allow_html=True,
            )
            if st.button(f"Open {d['name']}", key=f"o{i}"):
                go_device_detail(d["id"], d["name"])
                st.rerun()

# ---------------------------------------------------------
# PAGE: ADD DEVICE
# ---------------------------------------------------------
def page_add():
    st.title("➕ Add Device")
    name = st.text_input("Device Name")
    dev_id = st.text_input("Device ID")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save"):
            if name and dev_id:
                d = load_devices()
                d.append({"name": name, "id": dev_id})
                save_devices(d)
                st.success("Device added successfully.")
                go_mydevices()
                st.rerun()
            else:
                st.warning("Please enter both fields.")
    with c2:
        if st.button("Cancel"):
            go_home()
            st.rerun()

# ---------------------------------------------------------
# PAGE: MANAGE DEVICES
# ---------------------------------------------------------
def page_manage():
    st.title("⚙️ Manage Devices")
    devs = load_devices()
    if not devs:
        st.info("No devices found.")
        return

    for i, d in enumerate(devs):
        c1, c2, c3 = st.columns([3, 3, 1])
        with c1:
            new_name = st.text_input("Name", value=d["name"], key=f"n{i}")
        with c2:
            new_id = st.text_input("ID", value=d["id"], key=f"id{i}")
        with c3:
            if st.button("💾 Save", key=f"s{i}"):
                devs[i] = {"name": new_name, "id": new_id}
                save_devices(devs)
                st.success("Saved successfully.")
                st.rerun()
            if st.button("🗑 Delete", key=f"d{i}"):
                del devs[i]
                save_devices(devs)
                st.warning("Device deleted.")
                st.rerun()

# ---------------------------------------------------------
# PAGE: DEVICE DETAILS
# ---------------------------------------------------------
def page_device():
    did = st.session_state.get("current_device_id")
    dname = st.session_state.get("current_device_name")

    if not did:
        st.error("No device selected.")
        if st.button("⬅️ Back"):
            go_home()
            st.rerun()
        return

    st_autorefresh(interval=30000, key=f"r{did}")
    st.title(f"{dname} – Live Data")

    res = fetch_and_log_once(did, dname)
    if "error" in res:
        st.error(res["error"])
        if st.button("⬅️ Back"):
            go_home()
            st.rerun()
        return

    row = res.get("row", {})

    v = float(row.get("voltage", 0))
    p = float(row.get("power", 0))

    # Device Status Detection (Temporary)
    device_status = "ON" if p > 1 else "OFF"

    status_color = "#00ff9d" if device_status == "ON" else "#ff4d4d"

    st.markdown(f"""
        <div style="
        padding: 12px;
        text-align: center;
        background: rgba(0,20,50,0.55);
        border: 1px solid {status_color};
        border-radius: 10px;
        box-shadow: 0 0 15px {status_color}55;
        font-size: 20px;
        font-weight: 700;
        color: {status_color};
        margin-top: 10px;
        margin-bottom: 20px;
    ">
        Device Status: {device_status}
    </div>
""", unsafe_allow_html=True)


    # Gauges
        # st.subheader("🔋 Live Power & Voltage")
        # col1, col2, col3 = st.columns([1, 1, 2])

        # # Voltage Gauge
        # with col1:
        #     fig_v = go.Figure(go.Indicator(
        #         mode="gauge+number",
        #         value=v,
        #         title={'text': "Voltage (V)", 'font': {'color': '#00c2ff', 'size': 16}},
        #         gauge={
        #             'shape': 'angular',
        #             'axis': {'range': [0, max(250, v * 1.2)], 'tickcolor': '#00c2ff'},
        #             'bar': {'color': '#00c2ff'},
        #             'bgcolor': 'rgba(5,10,25,0.8)',
        #             'borderwidth': 2,
        #             'bordercolor': '#00c2ff'
        #         }
        #     ))
        #     fig_v.update_layout(
        #         template="plotly_dark",
        #         height=230,
        #         margin=dict(l=10, r=10, t=40, b=10),
        #         paper_bgcolor="rgba(0,0,0,0)",
        #         font=dict(color="#e6eef6")
        #     )
        #     st.plotly_chart(fig_v, use_container_width=True)

        # # Power Gauge
        # with col2:
        #     fig_p = go.Figure(go.Indicator(
        #         mode="gauge+number",
        #         value=p,
        #         title={'text': "Power (W)", 'font': {'color': '#00c2ff', 'size': 16}},
        #         gauge={
        #             'shape': 'angular',
        #             'axis': {'range': [0, max(1000, p * 1.5)], 'tickcolor': '#00c2ff'},
        #             'bar': {'color': '#00c2ff'},
        #             'bgcolor': 'rgba(5,10,25,0.8)',
        #             'borderwidth': 2,
        #             'bordercolor': '#00c2ff'
        #         }
        #     ))
        #     fig_p.update_layout(
        #         template="plotly_dark",
        #         height=230,
        #         margin=dict(l=10, r=10, t=40, b=10),
        #         paper_bgcolor="rgba(0,0,0,0)",
        #         font=dict(color="#e6eef6")
        #     )
        #     st.plotly_chart(fig_p, use_container_width=True)
    #st.subheader("🔋 Live Power, Voltage & Current")

    # Row 1 – three gauges
    g1, g2, g3 = st.columns(3)

    # --- Voltage Gauge ---
    with g1:
        fig_v = go.Figure(go.Indicator(
            mode="gauge+number",
            value=v,
             title={
            'text': "Voltage (V)",
            'font': {'color': '#00c2ff', 'size': 16}  # bigger, more visible
            },
            gauge={
                'axis': {'range': [0, max(250, v * 1.2)], 'tickcolor': '#00c2ff'},
                'bar': {'color': '#00c2ff'},
                'bgcolor': 'rgba(5,10,25,0.8)',
                'borderwidth': 2,
                'bordercolor': '#00c2ff'
            }
        ))
        fig_v.update_layout(
            template="plotly_dark",
            height=210,
            margin=dict(l=10, r=10, t=30, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6eef6")
        )
        st.plotly_chart(fig_v, use_container_width=True)

    # --- Power Gauge ---
    with g2:
        watt_value = p / 10  # convert mW → W

        fig_p = go.Figure(go.Indicator(
            mode="gauge+number",
            value=watt_value,
            title={
            'text': "Power (W)",
            'font': {'color': '#00c2ff', 'size': 16}  # bigger, more visible
            },
            gauge={
            'axis': {'range': [0, max(1, watt_value * 1.5)], 'tickcolor': '#00c2ff'},
            'bar': {'color': '#00c2ff'},
            'bgcolor': 'rgba(5,10,25,0.8)',
            'borderwidth': 2,
            'bordercolor': '#00c2ff'
            }
    ))

        fig_p.update_layout(
            template="plotly_dark",
            height=210,
            margin=dict(l=10, r=10, t=30, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6eef6")
    )
        st.plotly_chart(fig_p, use_container_width=True)

    # --- Current Gauge ---
    with g3:
        i = float(row.get("current", 0))
        fig_i = go.Figure(go.Indicator(
            mode="gauge+number",
            value=i,
            number={
            'suffix': " A",
            'font': {'size': 46, 'color': '#e6eef6'}
            },
            title={
            'text': "<b>Current (A)</b>",
            'font': {'color': '#00c2ff', 'size': 16}  # bigger, more visible
            },
            gauge={
                'axis': {'range': [0, max(20, i * 1.5)], 'tickcolor': '#00c2ff'},
                'bar': {'color': '#00c2ff'},
                'bgcolor': 'rgba(5,10,25,0.8)',
                'borderwidth': 2,
                'bordercolor': '#00c2ff'
            }
        ))
        fig_i.update_layout(
            template="plotly_dark",
            height=210,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e6eef6")
        )
        st.plotly_chart(fig_i, use_container_width=True)
    # Live Power Chart
    
    st.markdown("⚡ Recent Power")
    df_recent = latest_docs(did, n=30)
    if not df_recent.empty:
        df_recent = df_recent.copy()
        df_recent["power_w"] = df_recent["power"] / 10
        fig = px.line(
            df_recent,
            x="timestamp",
            y="power_w",
            markers=True,
            title="Live Power Trend"
            )
        fig.update_traces(line=dict(color="#00e6ff", width=2.5))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,10,30,1)",
            plot_bgcolor="rgba(0,10,30,1)",
            font=dict(color="#00e6ff"),
            hovermode="x unified",
            height=260,
            margin=dict(l=10, r=20, t=50, b=40)
            )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet.")

    # Controls
    cA, cB, cC = st.columns([1, 1, 2])
    with cA:
        if st.button("TURN ON"):
            try:
                st.info(control_device(did, get_token(), "switch_1", True))
            except Exception as e:
                st.error(e)
    with cB:
        if st.button("TURN OFF"):
            try:
                st.info(control_device(did, get_token(), "switch_1", False))
            except Exception as e:
                st.error(e)
    with cC:
        if st.button("⬅️ Back to Devices"):
            go_mydevices()
            st.rerun()

    # -----------------------------------------------------
    # BILLING SECTION — Neon Blue Card Style
    # -----------------------------------------------------
    st.markdown("<h3 style='color:#00e6ff;font-weight:700;'>💰 Bill Estimate</h3>", unsafe_allow_html=True)
    d_u, d_c, m_u, m_c = daily_monthly_for(did)

    st.markdown("""
        <style>
        .bill-card {
            background: rgba(0,20,50,0.6);
            border: 1px solid rgba(0,194,255,0.4);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 0 18px rgba(0,194,255,0.2);
            transition: 0.3s;
        }
        .bill-card:hover {
            transform: scale(1.03);
            box-shadow: 0 0 25px rgba(0,194,255,0.4);
        }
        .bill-label {
            font-size: 15px;
            color: #00bfff;
            font-weight: 600;
        }
        .bill-value {
            font-size: 26px;
            font-weight: 800;
            color: #fff;
            margin-top: 8px;
        }
        </style>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    labels = ["Today (kWh)", "Today (BDT)", "Month (kWh)", "Month (BDT)"]
    values = [d_u, d_c, m_u, m_c]

    for c, lbl, val in zip([c1, c2, c3, c4], labels, values):
        if "kWh" in lbl:
            formatted_val = f"{val:.3f}"
        else:
            formatted_val = f"{val:.2f}"

        with c:
            st.markdown(f"""
            <div class='bill-card'>
                <div class='bill-label'>{lbl}</div>
                <div class='bill-value'>{formatted_val}</div>
            </div>
            """, unsafe_allow_html=True)


    # -----------------------------------------------------
    # HISTORICAL DATA
    # -----------------------------------------------------
    st.markdown("### 🕰️ Historical Data")
    c1, c2, c3 = st.columns(3)
    with c1:
        start_date = st.date_input("Start", value=datetime.now().date() - timedelta(days=1))
    with c2:
        end_date = st.date_input("End", value=datetime.now().date())
    with c3:
        agg = st.selectbox("Aggregation", ["raw", "1-min", "5-min", "15-min"], index=1)

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    df = range_docs(did, start_dt, end_dt)

    if not df.empty:
        
        df = df.sort_values("timestamp").set_index("timestamp")
        df["power_w"] = df["power"] / 10
        if agg != "raw":
            df = df.resample({"1-min": "1T", "5-min": "5T", "15-min": "15T"}[agg]) \
                   .mean(numeric_only=True).dropna()
            
        

        plot_df = df.reset_index()
        fig = px.line(
            plot_df,
            x="timestamp",
            y="power_w",
            title=f"⚡ Power Over Time ({agg})",
            markers=(agg == "raw")
        )
        fig.update_traces(line=dict(color="#00e6ff", width=2.5))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,10,30,1)",
            plot_bgcolor="rgba(0,10,30,1)",
            font=dict(color="#00e6ff"),
            hovermode="x unified",
            height=400,
            margin=dict(l=20, r=20, t=60, b=40)
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(plot_df.tail(200))
    else:
        st.info("No data in selected range.")

# ---------------------------------------------------------
# PAGE: USER MANUAL
# ---------------------------------------------------------
def page_manual():
    st.markdown("""
        <h1 style='text-align:center;
                   color:#00e6ff;
                   font-family:Poppins,sans-serif;
                   font-weight:800;
                   font-size:2.2em;
                   letter-spacing:1px;'>
            📘 User Manual
        </h1>
        <p style='text-align:center;color:#99ccff;'>
            Your guide to getting started, mastering features, and fixing issues.
        </p><br>
    """, unsafe_allow_html=True)

    # Custom CSS for expanders
    st.markdown("""
        <style>
        [data-testid="stExpander"] {
            background: rgba(0, 20, 50, 0.45);
            border: 1px solid rgba(0,194,255,0.3);
            border-radius: 12px;
            margin-bottom: 18px;
            box-shadow: 0 0 10px rgba(0,194,255,0.15);
        }
        [data-testid="stExpander"]:hover {
            box-shadow: 0 0 25px rgba(0,194,255,0.35);
            transform: scale(1.01);
        }
        [data-testid="stExpander"] p {
            color: #d8ecff;
            line-height: 1.6;
            font-size: 15px;
        }
        [data-testid="stExpander"] strong {
            color: #00c2ff;
        }
        [data-testid="stExpanderHeader"] p {
            color: #00e6ff;
            font-weight: 700;
            font-size: 16px;
            letter-spacing: .5px;
        }
        </style>
    """, unsafe_allow_html=True)

    with st.expander("🚀 Getting Started", expanded=True):
        st.markdown("""
            Welcome to **Green Power Monitor** — a real-time energy management system that helps you
        monitor and control your smart plugs easily.

            **Setup Steps:**
            1. **Add a Device:** Go to ➕ Add → Enter your *Tuya Device ID* and name.  
            2. **Authorize Access:** Configure your Tuya API keys and MongoDB credentials.  
            3. **Dashboard:** View devices, consumption, and billing summary.  
            4. **Live Monitor:** Click any device for real-time voltage, current, and power.  
            5. **Billing:** View daily and monthly bill estimates.  

            
        """)

    with st.expander("⚙️ Features Guide"):
        st.markdown("""
            **🏠 Dashboard**  
        Displays summarized statistics — total devices, active power, voltage, and bill estimation.

        **⚡ My Devices**  
        Lists all connected smart plugs. You can open each device to monitor its data in real time.

        **➕ Add Device**  
        Register new Tuya smart plugs with your project credentials.

        **⚙️ Manage Devices**  
        Edit or delete existing devices quickly.

        **🔋 Device Page**  
        - *Live Gauges:* Half-arc accelerometer-style power & voltage meters.  
        - *Live Chart:* Neon-blue real-time power graph.  
        - *Billing:* Daily and monthly cost cards.  
        - *Historical Data:* Filter by custom date range with adjustable aggregation (1 min / 5 min / 15 min).  

        """)

    with st.expander("🧰 Troubleshooting"):
        st.markdown("""
            **1️⃣ No Data Appears**
            - Check your Tuya Device ID and API credentials.  
            - Verify MongoDB connection.
            - Ensure your smart plug is online and connected to the internet.

            **2️⃣ Token Error**
            - Ensure API endpoint (`tuyaeu.com`, `us`, or `cn`) matches your region.  
            - Enable "Smart Home Management" and "Device Control" APIs on Tuya Cloud.

            **Need Help?**
            Contact **akashsaha399180@gmail.com** or check Streamlit logs.
        """)

    st.markdown("""
        <hr style='border:1px solid rgba(0,194,255,0.3);margin-top:30px;'>
        <p style='text-align:center;font-size:13px;color:#00c2ff;'>
            
        </p>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# ROUTER
# ---------------------------------------------------------
r = st.session_state.route
if r == "home":
    page_home()
elif r == "mydevices":
    page_mydevices()
elif r == "add":
    page_add()
elif r == "manage":
    page_manage()
elif r == "device":
    page_device()
elif r == "manual":
    page_manual()
else:
    page_home()

# ---------------------------------------------------------
# FOOTER
# ---------------------------------------------------------
st.markdown("<div class='footer'><b>© 2025 Green Power Monitor · Developed by Akash Saha</b></div>", unsafe_allow_html=True)










