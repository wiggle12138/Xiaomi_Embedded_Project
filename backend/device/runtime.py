"""设备运行时状态（在线/异常/最后活跃）。"""

import threading
from datetime import datetime

DEVICE_RUNTIME_LOCK = threading.Lock()
DEVICE_RUNTIME = {
    "S1": {"status": "idle", "last_seen": None, "last_error": ""},
    "E1": {"status": "idle", "last_seen": None, "last_error": ""},
    "E2": {"status": "idle", "last_seen": None, "last_error": ""},
    "E3": {"status": "idle", "last_seen": None, "last_error": ""},
    "S3": {"status": "idle", "last_seen": None, "last_error": ""},
    "E4": {"status": "idle", "last_seen": None, "last_error": ""},
    "S4": {"status": "idle", "last_seen": None, "last_error": ""},
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def mark_device_success(device_id):
    if not device_id:
        return
    with DEVICE_RUNTIME_LOCK:
        if device_id not in DEVICE_RUNTIME:
            return
        DEVICE_RUNTIME[device_id]["status"] = "idle"
        DEVICE_RUNTIME[device_id]["last_seen"] = now_iso()
        DEVICE_RUNTIME[device_id]["last_error"] = ""


def mark_device_error(device_id, error):
    if not device_id:
        return
    with DEVICE_RUNTIME_LOCK:
        if device_id not in DEVICE_RUNTIME:
            return
        DEVICE_RUNTIME[device_id]["status"] = "error"
        DEVICE_RUNTIME[device_id]["last_seen"] = now_iso()
        DEVICE_RUNTIME[device_id]["last_error"] = str(error)


def runtime_of(device_id):
    with DEVICE_RUNTIME_LOCK:
        return dict(DEVICE_RUNTIME.get(device_id, {}))
