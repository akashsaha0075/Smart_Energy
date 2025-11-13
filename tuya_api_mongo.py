import os
from typing import List, Tuple
from datetime import datetime
import pandas as pd
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError
from dotenv import load_dotenv



load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB  = os.getenv("MONGODB_DB", "SmartHome")

_client = None
def get_client():
    global _client
    if _client is None and MONGODB_URI:
        _client = MongoClient(MONGODB_URI, tls=True)
    return _client

def _get_db(client):
    if client is None:
        return None
    try:
        db = client.get_default_database()
    except Exception:
        db = None
    if db is None:
        db = client[MONGODB_DB]
    return db

def get_collection(device_id: str):
    client = get_client()
    if client is None:
        return None
    db = _get_db(client)
    coll = db[f"readings_{device_id}"]
    try:
        coll.create_index([("timestamp", ASCENDING)])
    except Exception:
        pass
    return coll

def insert_reading(device_id: str, doc: dict) -> bool:
    coll = get_collection(device_id)
    if coll is None:
        return False
    try:
        coll.insert_one(doc)
        return True
    except PyMongoError:
        return False

# # ---------- NEW: Queries ----------
# def latest_docs(device_id: str, n: int = 100) -> pd.DataFrame:
#     coll = get_collection(device_id)
#     if coll is None:
#         return pd.DataFrame()
#     cur = coll.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(n)
#     df = pd.DataFrame(list(cur))
#     if df.empty:
#         return df
#     df["timestamp"] = pd.to_datetime(df["timestamp"])
#     df = df.sort_values("timestamp")  # ascending for charts
#     return df



# ---------- UPDATED: Queries ----------
def latest_docs(device_id: str, n: int = 100) -> pd.DataFrame:
    coll = get_collection(device_id)
    if coll is None:
        return pd.DataFrame()
    cur = coll.find({}, {"_id": 0}).sort("timestamp", DESCENDING).limit(n)
    df = pd.DataFrame(list(cur))
    if df.empty:
        return df

    # Convert UTC → Dhaka (GMT+6)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Dhaka")

    df = df.sort_values("timestamp")  # ascending for charts
    return df


def range_docs(device_id: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    coll = get_collection(device_id)
    if coll is None:
        return pd.DataFrame()
    q = {"timestamp": {"$gte": start_dt, "$lte": end_dt}}
    cur = coll.find(q, {"_id": 0}).sort("timestamp", ASCENDING)
    df = pd.DataFrame(list(cur))
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Dhaka")

    df = df.sort_values("timestamp")  # ascending for charts
    
    return df
