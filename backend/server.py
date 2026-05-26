#!/usr/bin/env python3
import json
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import wake_worker


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
BIN_DIR = ROOT_DIR / "bin"
AUDIO_DIR = ROOT_DIR / "logs" / "audio-check"
HOST = os.environ.get("TASK1_HOST", "0.0.0.0")
PORT = int(os.environ.get("TASK1_PORT", "8080"))


STATE_LOCK = threading.Lock()
CMD_LOCK = threading.Lock()
STATE = {
    "fan": {"on": False, "speed": 0},
    "light": {"on": False, "r": 255, "g": 255, "b": 255, "brightness": 100},
    "curtain": {"position": 0},
}
AUDIO_LOCK = threading.Lock()
VOICE_SESSION_LOCK = threading.Lock()
VOICE_SESSION = {
    "active": False,
    "proc": None,
    "audio_file": None,
    "start_ts": 0.0,
    "max_seconds": 0,
    "rate": 16000,
}


def clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, value))


def run_cmd(args):
    cmd = [str(BIN_DIR / args[0]), *[str(x) for x in args[1:]]]
    with CMD_LOCK:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "unknown command error"
        raise RuntimeError(err)
    return proc.stdout.strip()


def _safe_audio_seconds(value):
    return clamp(int(value), 1, 10)


def record_audio(seconds=3, rate=16000):
    seconds = _safe_audio_seconds(seconds)
    rate = clamp(int(rate), 8000, 48000)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUDIO_DIR / f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

    tinycap_card = os.environ.get("S3_CARD", "0")
    tinycap_device = os.environ.get("S3_PCM_DEVICE", "0")
    alsa_device = os.environ.get("S3_DEVICE", "default")

    if not shutil.which("tinycap") and not shutil.which("arecord"):
        raise RuntimeError("未找到 tinycap/arecord，无法录音")

    with AUDIO_LOCK:
        if shutil.which("tinycap"):
            cmd = [
                "tinycap",
                str(out_path),
                "-D",
                str(tinycap_card),
                "-d",
                str(tinycap_device),
                "-t",
                str(seconds),
                "-b",
                "16",
                "-r",
                str(rate),
            ]
        else:
            cmd = [
                "arecord",
                "-D",
                str(alsa_device),
                "-f",
                "S16_LE",
                "-r",
                str(rate),
                "-c",
                "1",
                "-d",
                str(seconds),
                str(out_path),
            ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds + 5)

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "录音失败"
        raise RuntimeError(err)

    return out_path


def playback_audio(audio_path):
    path = Path(audio_path)
    if not path.exists():
        raise ValueError(f"音频文件不存在: {path}")
    if not shutil.which("tinyplay") and not shutil.which("aplay"):
        raise RuntimeError("未找到 tinyplay/aplay，无法回放")

    tinyplay_card = os.environ.get("E4_CARD", "0")
    tinyplay_device = os.environ.get("E4_PCM_DEVICE", "1")
    rate = os.environ.get("E4_RATE", "16000")

    with AUDIO_LOCK:
        if shutil.which("tinyplay"):
            cmd = [
                "tinyplay",
                "-D",
                str(tinyplay_card),
                "-d",
                str(tinyplay_device),
                "-r",
                str(rate),
                str(path),
            ]
        else:
            cmd = ["aplay", str(path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "回放失败"
        raise RuntimeError(err)
    return True


def speak_wake_reply():
    """扬声器回复：播放 assets/speech/reply.wav（自行录制）。"""
    wav = os.environ.get("WAKE_REPLY_WAV", str(ROOT_DIR / "assets/speech/reply.wav"))
    path = Path(wav)
    if not path.is_file():
        print(f"[project] 未找到回复音频 {path}，请将 reply.wav 放入 assets/speech/")
        return
    playback_audio(path)


def latest_audio_file():
    if not AUDIO_DIR.exists():
        return None
    files = sorted([p for p in AUDIO_DIR.glob("*.wav") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _voice_snapshot():
    with VOICE_SESSION_LOCK:
        active = VOICE_SESSION["active"]
        start_ts = VOICE_SESSION["start_ts"]
        max_seconds = VOICE_SESSION["max_seconds"]
        audio_file = VOICE_SESSION["audio_file"]
    elapsed = max(0, int(time.time() - start_ts)) if active and start_ts > 0 else 0
    remaining = max(0, max_seconds - elapsed) if active else 0
    return {
        "active": active,
        "audio_file": str(audio_file) if audio_file else None,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "max_seconds": max_seconds,
    }


def _voice_auto_stop_worker():
    while True:
        with VOICE_SESSION_LOCK:
            if not VOICE_SESSION["active"]:
                return
            proc = VOICE_SESSION["proc"]
            start_ts = VOICE_SESSION["start_ts"]
            max_seconds = VOICE_SESSION["max_seconds"]
        if time.time() - start_ts >= max_seconds:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
            with VOICE_SESSION_LOCK:
                VOICE_SESSION["active"] = False
                VOICE_SESSION["proc"] = None
            return
        time.sleep(0.2)


def start_voice_session(max_seconds=60, rate=16000):
    max_seconds = clamp(int(max_seconds), 1, 60)
    rate = clamp(int(rate), 8000, 48000)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUDIO_DIR / f"voice_hold_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

    if not shutil.which("arecord"):
        raise RuntimeError("按住说话模式需要 arecord，请先安装 alsa-utils")
    alsa_device = os.environ.get("S3_DEVICE", "default")
    cmd = [
        "arecord",
        "-D",
        str(alsa_device),
        "-f",
        "S16_LE",
        "-r",
        str(rate),
        "-c",
        "1",
        str(out_path),
    ]

    with VOICE_SESSION_LOCK:
        if VOICE_SESSION["active"]:
            raise ValueError("已有录音会话在进行中")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        VOICE_SESSION["active"] = True
        VOICE_SESSION["proc"] = proc
        VOICE_SESSION["audio_file"] = out_path
        VOICE_SESSION["start_ts"] = time.time()
        VOICE_SESSION["max_seconds"] = max_seconds
        VOICE_SESSION["rate"] = rate

    threading.Thread(target=_voice_auto_stop_worker, daemon=True).start()
    return out_path


def stop_voice_session():
    with VOICE_SESSION_LOCK:
        if not VOICE_SESSION["active"]:
            raise ValueError("当前没有正在进行的录音会话")
        proc = VOICE_SESSION["proc"]
        out_path = VOICE_SESSION["audio_file"]
        start_ts = VOICE_SESSION["start_ts"]
        VOICE_SESSION["active"] = False
        VOICE_SESSION["proc"] = None

    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)

    duration = max(0.0, time.time() - start_ts)
    if not out_path or not Path(out_path).exists():
        raise RuntimeError("录音文件未生成，请重试")
    return Path(out_path), duration




def _snapshot_state():
    with STATE_LOCK:
        return json.loads(json.dumps(STATE))


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        return v in ("1", "true", "yes", "on", "open", "开启", "打开")
    return bool(value)


def do_fan_power(on):
    if on:
        with STATE_LOCK:
            speed = STATE["fan"]["speed"]
            speed = 30 if speed <= 0 else speed
        run_cmd(["e2_ctl", "speed", speed])
        with STATE_LOCK:
            STATE["fan"]["on"] = True
            STATE["fan"]["speed"] = speed
        return f"风扇已开启，速度 {speed}"

    run_cmd(["e2_ctl", "off"])
    with STATE_LOCK:
        STATE["fan"]["on"] = False
        STATE["fan"]["speed"] = 0
    return "风扇已关闭"


def do_fan_speed(speed):
    speed = clamp(int(speed), 0, 100)
    run_cmd(["e2_ctl", "speed", speed])
    with STATE_LOCK:
        STATE["fan"]["speed"] = speed
        STATE["fan"]["on"] = speed > 0
    return f"风扇速度已设置为 {speed}"


def do_light_power(on):
    if not on:
        run_cmd(["e1_ctl", "off"])
        with STATE_LOCK:
            STATE["light"]["on"] = False
        return "灯已关闭"

    with STATE_LOCK:
        r = STATE["light"]["r"]
        g = STATE["light"]["g"]
        b = STATE["light"]["b"]
        brightness = STATE["light"]["brightness"]
    run_cmd(["e1_ctl", "rgb", r, g, b, brightness])
    with STATE_LOCK:
        STATE["light"]["on"] = True
    return "灯已开启"


def do_light_rgb(r=None, g=None, b=None, brightness=None):
    with STATE_LOCK:
        old = json.loads(json.dumps(STATE["light"]))
    r = old["r"] if r is None else clamp(int(r), 0, 255)
    g = old["g"] if g is None else clamp(int(g), 0, 255)
    b = old["b"] if b is None else clamp(int(b), 0, 255)
    brightness = old["brightness"] if brightness is None else clamp(int(brightness), 0, 100)

    run_cmd(["e1_ctl", "rgb", r, g, b, brightness])
    with STATE_LOCK:
        STATE["light"]["on"] = (brightness > 0 and (r > 0 or g > 0 or b > 0))
        STATE["light"]["r"] = r
        STATE["light"]["g"] = g
        STATE["light"]["b"] = b
        STATE["light"]["brightness"] = brightness
    return "灯光参数已更新"


def do_curtain_position(position):
    position = clamp(int(position), 0, 100)
    run_cmd(["e3_ctl", "position", position])
    with STATE_LOCK:
        STATE["curtain"]["position"] = position
    return f"窗帘开度已设置为 {position}"


def execute_action(action, source="structured"):
    if not isinstance(action, dict):
        raise ValueError("command 必须是 JSON 对象")

    device = str(action.get("device", "")).strip().lower()
    act = str(action.get("action", "")).strip().lower()
    params = action.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("params 必须是 JSON 对象")

    message = None

    if device == "fan":
        if act == "on":
            message = do_fan_power(True)
        elif act == "off":
            message = do_fan_power(False)
        elif act == "set_speed":
            speed = params.get("speed", 0)
            message = do_fan_speed(speed)
        else:
            raise ValueError("fan action 不支持")
    elif device == "light":
        if act == "on":
            message = do_light_power(True)
        elif act == "off":
            message = do_light_power(False)
        elif act == "set_rgb":
            message = do_light_rgb(
                r=params.get("r"),
                g=params.get("g"),
                b=params.get("b"),
                brightness=params.get("brightness"),
            )
        elif act == "set_brightness":
            message = do_light_rgb(brightness=params.get("brightness"))
        else:
            raise ValueError("light action 不支持")
    elif device == "curtain":
        if act == "open":
            message = do_curtain_position(100)
        elif act == "close":
            message = do_curtain_position(0)
        elif act == "set_position":
            position = params.get("position", 0)
            message = do_curtain_position(position)
        else:
            raise ValueError("curtain action 不支持")
    else:
        raise ValueError("device 不支持")

    return {
        "source": source,
        "action": {"device": device, "action": act, "params": params},
        "message": message,
        "state": _snapshot_state(),
    }


def _extract_percent(text):
    match = re.search(r"(\d{1,3})\s*%?", text)
    if not match:
        return None
    return clamp(int(match.group(1)), 0, 100)


def parse_text_to_action(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text 不能为空")

    t = re.sub(r"\s+", "", text.lower())

    # 窗帘
    if "窗帘" in t:
        if any(k in t for k in ("打开", "开窗帘", "全开")):
            return {"device": "curtain", "action": "open", "params": {}}
        if any(k in t for k in ("关闭", "关窗帘", "全关")):
            return {"device": "curtain", "action": "close", "params": {}}
        if "半开" in t:
            return {"device": "curtain", "action": "set_position", "params": {"position": 50}}
        if any(k in t for k in ("开度", "位置", "调到", "到")):
            pos = _extract_percent(t)
            if pos is not None:
                return {"device": "curtain", "action": "set_position", "params": {"position": pos}}

    # 风扇
    if "风扇" in t:
        if any(k in t for k in ("关闭", "关掉", "停止")):
            return {"device": "fan", "action": "off", "params": {}}
        if any(k in t for k in ("打开", "开启")):
            return {"device": "fan", "action": "on", "params": {}}
        if any(k in t for k in ("速度", "调速", "转速")):
            speed = _extract_percent(t)
            if speed is not None:
                return {"device": "fan", "action": "set_speed", "params": {"speed": speed}}

    # 灯
    if any(k in t for k in ("灯", "灯光")):
        if any(k in t for k in ("关灯", "关闭", "熄灭")):
            return {"device": "light", "action": "off", "params": {}}
        if any(k in t for k in ("开灯", "打开", "开启")):
            return {"device": "light", "action": "on", "params": {}}

        rgb_map = {
            "红": (255, 0, 0),
            "绿": (0, 255, 0),
            "蓝": (0, 0, 255),
            "白": (255, 255, 255),
            "橙": (255, 128, 0),
            "黄": (255, 255, 0),
            "紫": (128, 0, 128),
        }
        for keyword, rgb in rgb_map.items():
            if keyword in t:
                action = {
                    "device": "light",
                    "action": "set_rgb",
                    "params": {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
                }
                brightness = _extract_percent(t)
                if brightness is not None and any(k in t for k in ("亮度", "调亮")):
                    action["params"]["brightness"] = brightness
                return action

        if "亮度" in t:
            brightness = _extract_percent(t)
            if brightness is not None:
                return {"device": "light", "action": "set_brightness", "params": {"brightness": brightness}}

    raise ValueError("暂不支持该自然语言指令，请改用结构化 command")


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        content_len = int(self.headers.get("Content-Length", "0"))
        if content_len <= 0:
            return {}
        raw = self.rfile.read(content_len).decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)

    def _serve_file(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "Not Found")
            return
        content = file_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(200, {"ok": True})
            return
        if path == "/api/state":
            self._send_json(200, {"ok": True, "data": _snapshot_state()})
            return
        if path == "/api/voice/latest":
            latest = latest_audio_file()
            self._send_json(200, {"ok": True, "data": {"audio_file": str(latest) if latest else None}})
            return
        if path == "/api/voice/status":
            self._send_json(200, {"ok": True, "data": _voice_snapshot()})
            return
        if path == "/api/wake/status":
            self._send_json(200, {"ok": True, "data": wake_worker.snapshot()})
            return

        if path in ("/", "/index.html"):
            self._serve_file(FRONTEND_DIR / "index.html")
            return
        if path == "/app.js":
            self._serve_file(FRONTEND_DIR / "app.js")
            return
        if path == "/style.css":
            self._serve_file(FRONTEND_DIR / "style.css")
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "JSON 格式错误"})
            return

        try:
            if path == "/api/fan/power":
                result = execute_action(
                    {"device": "fan", "action": "on" if _as_bool(payload.get("on", False)) else "off", "params": {}},
                    source="http",
                )
            elif path == "/api/fan/speed":
                result = execute_action(
                    {"device": "fan", "action": "set_speed", "params": {"speed": payload.get("speed", 0)}},
                    source="http",
                )
            elif path == "/api/light/power":
                result = execute_action(
                    {"device": "light", "action": "on" if _as_bool(payload.get("on", False)) else "off", "params": {}},
                    source="http",
                )
            elif path == "/api/light/rgb":
                result = execute_action(
                    {
                        "device": "light",
                        "action": "set_rgb",
                        "params": {
                            "r": payload.get("r"),
                            "g": payload.get("g"),
                            "b": payload.get("b"),
                            "brightness": payload.get("brightness"),
                        },
                    },
                    source="http",
                )
            elif path == "/api/curtain/open":
                result = execute_action({"device": "curtain", "action": "open", "params": {}}, source="http")
            elif path == "/api/curtain/close":
                result = execute_action({"device": "curtain", "action": "close", "params": {}}, source="http")
            elif path == "/api/curtain/position":
                result = execute_action(
                    {
                        "device": "curtain",
                        "action": "set_position",
                        "params": {"position": payload.get("position", 0)},
                    },
                    source="http",
                )
            elif path == "/api/ai/command":
                if isinstance(payload.get("command"), dict):
                    result = execute_action(payload["command"], source="structured")
                else:
                    text = payload.get("text", "")
                    action = parse_text_to_action(text)
                    result = execute_action(action, source="text")
                    result["text"] = text
            elif path == "/api/voice/record":
                seconds = payload.get("seconds", 3)
                rate = payload.get("rate", 16000)
                file_path = record_audio(seconds=seconds, rate=rate)
                result = {
                    "source": "voice",
                    "message": "录音完成",
                    "audio_file": str(file_path),
                    "state": _snapshot_state(),
                }
            elif path == "/api/voice/start":
                max_seconds = payload.get("max_seconds", 60)
                rate = payload.get("rate", 16000)
                file_path = start_voice_session(max_seconds=max_seconds, rate=rate)
                result = {
                    "source": "voice",
                    "message": "录音已开始",
                    "audio_file": str(file_path),
                    "voice_status": _voice_snapshot(),
                    "state": _snapshot_state(),
                }
            elif path == "/api/voice/stop":
                file_path, duration = stop_voice_session()
                result = {
                    "source": "voice",
                    "message": f"录音已停止，时长 {duration:.1f}s",
                    "audio_file": str(file_path),
                    "duration_seconds": round(duration, 1),
                    "voice_status": _voice_snapshot(),
                    "state": _snapshot_state(),
                }
                transcript = str(payload.get("mock_text", "")).strip()
                if transcript:
                    action = parse_text_to_action(transcript)
                    exec_result = execute_action(action, source="voice")
                    result["message"] = exec_result["message"]
                    result["action"] = exec_result["action"]
                    result["state"] = exec_result["state"]
                    result["transcript"] = transcript
            elif path == "/api/voice/playback":
                audio_file = payload.get("audio_file")
                if audio_file:
                    target = Path(audio_file)
                else:
                    target = latest_audio_file()
                    if not target:
                        raise ValueError("未找到可回放的录音文件")
                playback_audio(target)
                result = {
                    "source": "voice",
                    "message": "回放完成",
                    "audio_file": str(target),
                    "state": _snapshot_state(),
                }
            elif path == "/api/voice/command":
                # P1最小语音链路：录音 -> (mock文本) -> 文本解析 -> 动作执行
                seconds = payload.get("seconds", 3)
                rate = payload.get("rate", 16000)
                file_path = record_audio(seconds=seconds, rate=rate)

                transcript = str(payload.get("mock_text", "")).strip()
                if not transcript:
                    raise ValueError("当前为语音链路第一版，请传入 mock_text 作为识别文本")

                action = parse_text_to_action(transcript)
                result = execute_action(action, source="voice")
                result["audio_file"] = str(file_path)
                result["transcript"] = transcript
            else:
                self._send_json(404, {"ok": False, "error": "接口不存在"})
                return
            self._send_json(200, {"ok": True, "data": result, "message": result["message"]})
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        # 保留简洁日志，方便现场调试
        print("[project]", fmt % args)


def main():
    wake_worker.set_speak_fn(speak_wake_reply)
    wake_worker.try_start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"project server listening on http://{HOST}:{PORT}")
    print(f"frontend root: {FRONTEND_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
