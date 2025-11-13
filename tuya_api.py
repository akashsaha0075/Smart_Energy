import os, time, json, hmac, hashlib, requests
from dotenv import load_dotenv

load_dotenv()
ACCESS_ID = os.getenv("TUYA_ACCESS_ID", "")
ACCESS_SECRET = os.getenv("TUYA_ACCESS_SECRET", "")
API_ENDPOINT = os.getenv("TUYA_API_ENDPOINT", "https://openapi.tuyaeu.com")
HTTP_TIMEOUT = 15

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

_token_cache = {"value": None, "ts": 0, "ttl": 55}  # seconds

def get_token():
    now = time.time()
    if _token_cache["value"] and (now - _token_cache["ts"] < _token_cache["ttl"]):
        return _token_cache["value"]
    path = "/v1.0/token?grant_type=1"
    sign, t = _make_sign(ACCESS_ID, ACCESS_SECRET, "GET", path)
    headers = {"client_id": ACCESS_ID, "sign": sign, "t": t, "sign_method": "HMAC-SHA256"}
    res = requests.get(API_ENDPOINT + path, headers=headers, timeout=HTTP_TIMEOUT)
    data = res.json()
    if not data.get("success"):
        raise RuntimeError(f"Failed to get token: {data}")
    _token_cache["value"] = data["result"]["access_token"]
    _token_cache["ts"] = now
    return _token_cache["value"]

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
