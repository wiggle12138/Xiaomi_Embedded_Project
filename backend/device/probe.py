"""设备探测与 /api/devices 快照。"""

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from device.runtime import now_iso, runtime_of
from voice import wake_worker
from voice.audio_io import voice_snapshot

I2C_SCAN_CACHE_LOCK = threading.Lock()
I2C_SCAN_CACHE = {"ts": 0.0, "buses": {}}
I2C_SCAN_TTL_SECONDS = 3.0


def _detect_i2c_device_nodes():
    nodes = sorted(Path("/dev").glob("i2c-*"))
    buses = []
    for node in nodes:
        suffix = node.name.replace("i2c-", "")
        if suffix.isdigit():
            buses.append(int(suffix))
    return buses


def _parse_i2cdetect_output(raw):
    present = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        if line.startswith("Error"):
            continue
        _, rhs = line.split(":", 1)
        for token in rhs.split():
            token = token.strip().lower()
            if len(token) == 2 and all(c in "0123456789abcdef" for c in token):
                present.add(int(token, 16))
    return present


def _scan_i2c_addrs():
    now = time.time()
    with I2C_SCAN_CACHE_LOCK:
        if now - I2C_SCAN_CACHE["ts"] <= I2C_SCAN_TTL_SECONDS:
            return dict(I2C_SCAN_CACHE["buses"])

    if not shutil.which("i2cdetect"):
        return {}

    buses = _detect_i2c_device_nodes()
    result = {}
    for bus in buses:
        cmd = ["i2cdetect", "-y", "-a", str(bus)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        except Exception:
            continue
        if proc.returncode != 0:
            continue
        result[bus] = _parse_i2cdetect_output(proc.stdout)

    with I2C_SCAN_CACHE_LOCK:
        I2C_SCAN_CACHE["ts"] = now
        I2C_SCAN_CACHE["buses"] = dict(result)
    return result


def _i2c_target_present(scan_map, candidate_addrs):
    if not scan_map:
        return False
    target = set(candidate_addrs)
    for found in scan_map.values():
        if target.intersection(found):
            return True
    return False


def device_snapshot():
    wake = wake_worker.snapshot()
    voice = voice_snapshot()
    i2c_scan = _scan_i2c_addrs()

    addr_s1_keys = [0x74, 0x75, 0x76, 0x77]
    addr_e1_light = [0x60, 0x61, 0x62, 0x63]
    addr_e1_display = [0x70, 0x71, 0x72, 0x73]
    addr_e2_fan = [0x64, 0x65, 0x66, 0x67]
    addr_e3_motor = [0x1C, 0x1D, 0x1E, 0x1F]

    s1_runtime = runtime_of("S1")
    e1_runtime = runtime_of("E1")
    e2_runtime = runtime_of("E2")
    e3_runtime = runtime_of("E3")
    s3_runtime = runtime_of("S3")
    e4_runtime = runtime_of("E4")
    s4_runtime = runtime_of("S4")

    s3_status = "busy" if voice["active"] or wake.get("kws_listening") else s3_runtime.get("status", "idle")
    s3_online = (shutil.which("tinycap") or shutil.which("arecord")) and Path("/dev/snd").exists()
    e4_online = (shutil.which("tinyplay") or shutil.which("aplay")) and Path("/dev/snd").exists()
    s4_online = Path(f"/dev/video{str(os.environ.get('S4_VIDEO_DEVICE', '8'))}").exists()

    devices = [
        {
            "device_id": "S1",
            "name": "按键子板",
            "type": "key",
            "online": bool(_i2c_target_present(i2c_scan, addr_s1_keys)),
            "status": s1_runtime.get("status", "idle"),
            "capabilities": ["key.read"],
            "last_seen": s1_runtime.get("last_seen"),
            "last_error": s1_runtime.get("last_error", ""),
        },
        {
            "device_id": "E1",
            "name": "灯光子板",
            "type": "light",
            "online": bool(_i2c_target_present(i2c_scan, addr_e1_light + addr_e1_display)),
            "status": e1_runtime.get("status", "idle"),
            "capabilities": ["light.on", "light.off", "light.set_rgb", "light.set_brightness"],
            "last_seen": e1_runtime.get("last_seen"),
            "last_error": e1_runtime.get("last_error", ""),
        },
        {
            "device_id": "E2",
            "name": "风扇子板",
            "type": "fan",
            "online": bool(_i2c_target_present(i2c_scan, addr_e2_fan)),
            "status": e2_runtime.get("status", "idle"),
            "capabilities": ["fan.on", "fan.off", "fan.set_speed"],
            "last_seen": e2_runtime.get("last_seen"),
            "last_error": e2_runtime.get("last_error", ""),
        },
        {
            "device_id": "E3",
            "name": "窗帘子板",
            "type": "curtain",
            "online": bool(_i2c_target_present(i2c_scan, addr_e3_motor)),
            "status": e3_runtime.get("status", "idle"),
            "capabilities": ["curtain.open", "curtain.close", "curtain.set_position"],
            "last_seen": e3_runtime.get("last_seen"),
            "last_error": e3_runtime.get("last_error", ""),
        },
        {
            "device_id": "S3",
            "name": "麦克风子板",
            "type": "mic",
            "online": bool(s3_online),
            "status": s3_status,
            "capabilities": ["voice.record", "wake.listen"],
            "last_seen": s3_runtime.get("last_seen"),
            "last_error": s3_runtime.get("last_error", ""),
        },
        {
            "device_id": "E4",
            "name": "扬声器子板",
            "type": "speaker",
            "online": bool(e4_online),
            "status": e4_runtime.get("status", "idle"),
            "capabilities": ["voice.playback", "wake.reply"],
            "last_seen": e4_runtime.get("last_seen"),
            "last_error": e4_runtime.get("last_error", ""),
        },
        {
            "device_id": "S4",
            "name": "摄像头子板",
            "type": "camera",
            "online": bool(s4_online),
            "status": s4_runtime.get("status", "idle"),
            "capabilities": ["vision.detect"],
            "last_seen": s4_runtime.get("last_seen"),
            "last_error": s4_runtime.get("last_error", ""),
        },
    ]

    for d in devices:
        if not d["online"] and d["status"] != "error":
            d["status"] = "offline"

    summary = {
        "total": len(devices),
        "online": sum(1 for d in devices if d["online"]),
        "offline": sum(1 for d in devices if not d["online"]),
        "error": sum(1 for d in devices if d["status"] == "error"),
        "busy": sum(1 for d in devices if d["status"] == "busy"),
    }
    return {
        "summary": summary,
        "devices": devices,
        "updated_at": now_iso(),
        "probe": {
            "i2c_tool": bool(shutil.which("i2cdetect")),
            "i2c_buses_scanned": sorted(list(i2c_scan.keys())),
        },
    }
