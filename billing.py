from datetime import datetime
import pandas as pd
from tuya_api_mongo import range_docs, latest_docs
from datetime import timedelta


# Bangladesh slab rates (example)
RATES = [
    (50, 4.63), (75, 5.26), (200, 7.20), (300, 7.59),
    (400, 8.02), (600, 12.67), (float("inf"), 14.61)
]

def _tier_cost(units_kwh: float) -> float:
    remaining, last_upper, cost = units_kwh, 0, 0.0
    for upper, rate in RATES:
        if remaining <= 0: break
        slab = min(remaining, upper - last_upper)
        cost += slab * rate
        remaining -= slab
        last_upper = upper
    return round(cost, 2)

def daily_monthly_for(device_id: str):
    now = datetime.now()
    # day range
    day_start = datetime(now.year, now.month, now.day)
    day_end   = datetime(now.year, now.month, now.day, 23, 59, 59, 999999)
    ddf = range_docs(device_id, day_start, day_end)
    d_units = round(float(ddf["energy_kWh"].sum()) if not ddf.empty else 0.0, 3)
    d_cost  = _tier_cost(d_units)

    # month range
    m_start = datetime(now.year, now.month, 1)
    # naive month-end
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1)
    else:
        next_month = datetime(now.year, now.month + 1, 1)
    m_end = next_month.replace(hour=0, minute=0, second=0, microsecond=0)
    mdf = range_docs(device_id, m_start, m_end)
    m_units = round(float(mdf["energy_kWh"].sum()) if not mdf.empty else 0.0, 3)
    m_cost  = _tier_cost(m_units)
    return d_units, d_cost, m_units, m_cost



def _latest_power_voltage(device_id: str):
    df = latest_docs(device_id, n=1)
    if df.empty:
        return 0.0, None
    row = df.iloc[-1]
    p = float(row.get("power", 0) or 0)
    v = row.get("voltage", None)
    v = float(v) if v is not None else None
    return p, v

def aggregate_totals_all_devices(devices: list[str|dict]):
    """Return (total_power_now_W, present_voltage_max_V, today_kwh, today_bill_bdt, month_kwh, month_bill_bdt)"""
    dev_ids = [d["id"] if isinstance(d, dict) else d for d in devices]

    # ---- Instant totals ----
    total_power_now = 0.0
    latest_voltages = []
    for did in dev_ids:
        p, v = _latest_power_voltage(did)
        total_power_now += p
        if v is not None:
            latest_voltages.append(float(v))
    present_voltage = round(max(latest_voltages), 2) if latest_voltages else 0.0

    # ---- Today (Dhaka local naive) ----
    now = datetime.now()
    day_start = datetime(now.year, now.month, now.day)
    day_end   = datetime(now.year, now.month, now.day, 23, 59, 59, 999999)

    total_kwh_today = 0.0
    for did in dev_ids:
        ddf = range_docs(did, day_start, day_end)
        if not ddf.empty and "energy_kWh" in ddf.columns:
            total_kwh_today += float(ddf["energy_kWh"].sum())
    total_kwh_today = round(total_kwh_today, 3)
    today_bill_bdt  = _tier_cost(total_kwh_today)

    # ---- This month ----
    m_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1)
    else:
        next_month = datetime(now.year, now.month + 1, 1)
    m_end = next_month.replace(hour=0, minute=0, second=0, microsecond=0)

    total_kwh_month = 0.0
    for did in dev_ids:
        mdf = range_docs(did, m_start, m_end)
        if not mdf.empty and "energy_kWh" in mdf.columns:
            total_kwh_month += float(mdf["energy_kWh"].sum())
    total_kwh_month = round(total_kwh_month, 3)
    month_bill_bdt  = _tier_cost(total_kwh_month)

    return (
        round(total_power_now, 2),
        present_voltage,
        total_kwh_today,
        today_bill_bdt,
        total_kwh_month,
        month_bill_bdt,
    )









def aggregate_timeseries_24h(devices: list[str|dict], resample_rule="5T") -> pd.DataFrame:
    """Return DataFrame with columns: timestamp, power_sum_W, voltage_avg_V for last 24h."""
    dev_ids = [d["id"] if isinstance(d, dict) else d for d in devices]
    end = datetime.now()
    start = end - timedelta(hours=24)

    frames = []
    for did in dev_ids:
        df = range_docs(did, start, end)
        if df.empty:
            continue
        cols = [c for c in ["timestamp", "power", "voltage"] if c in df.columns]
        if "timestamp" not in cols:
            continue
        df = df[cols].sort_values("timestamp").set_index("timestamp")
        df = df.resample(resample_rule).mean(numeric_only=True)
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["timestamp", "power_sum_W", "voltage_avg_V"])

    aligned = pd.concat(frames, axis=1, keys=range(len(frames)))
    power_cols   = [c for c in aligned.columns if c[1] == "power"]
    voltage_cols = [c for c in aligned.columns if c[1] == "voltage"]

    out = pd.DataFrame({
        "power_sum_W": aligned[power_cols].sum(axis=1, min_count=1),
        "voltage_avg_V": aligned[voltage_cols].mean(axis=1)
    })
    out = out.dropna(how="all")
    out = out.reset_index().rename(columns={"index": "timestamp"})
    return out


