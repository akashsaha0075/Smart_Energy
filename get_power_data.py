from tuya_api import get_token, get_device_status
from tuya_api_mongo import insert_reading
from helpers import parse_metrics, build_doc

def fetch_and_log_once(device_id: str, device_name: str = ""):
    token = get_token()
    raw = get_device_status(device_id, token)
    if not raw.get("success"):
        return {"error": raw}
    v, c, p, e = parse_metrics(raw)
    doc = build_doc(device_id, device_name, v, c, p, e)
    insert_reading(device_id, doc)
    return {"ok": True, "row": doc, "raw": raw}
