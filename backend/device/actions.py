"""E 子板控制：状态、指令执行、自然语言直解析。"""

import json
import re
import subprocess
import threading

from config.paths import BIN_DIR
from config.util import clamp
from device.runtime import mark_device_error, mark_device_success

STATE_LOCK = threading.Lock()
CMD_LOCK = threading.Lock()
STATE = {
    "fan": {"on": False, "speed": 0},
    "light": {"on": False, "r": 255, "g": 255, "b": 255, "brightness": 100},
    "curtain": {"position": 0},
}


def run_cmd(args):
    cmd = [str(BIN_DIR / args[0]), *[str(x) for x in args[1:]]]
    with CMD_LOCK:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "unknown command error"
        raise RuntimeError(err)
    return proc.stdout.strip()


def snapshot_state():
    with STATE_LOCK:
        return json.loads(json.dumps(STATE))


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
    board_map = {"light": "E1", "fan": "E2", "curtain": "E3"}
    board_id = board_map.get(device)
    try:
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
    except Exception as exc:
        mark_device_error(board_id, exc)
        raise

    mark_device_success(board_id)

    return {
        "source": source,
        "action": {"device": device, "action": act, "params": params},
        "message": message,
        "state": snapshot_state(),
    }


def _extract_percent(text):
    match = re.search(r"(\d{1,3})\s*%?", text)
    if not match:
        return None
    return clamp(int(match.group(1)), 0, 100)


def parse_text_to_action(text, state=None):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text 不能为空")

    if state is None:
        state = snapshot_state()

    t = re.sub(r"\s+", "", text.lower())

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

    if "风扇" in t:
        if any(k in t for k in ("关闭", "关掉", "停止")):
            return {"device": "fan", "action": "off", "params": {}}
        if any(k in t for k in ("打开", "开启")):
            return {"device": "fan", "action": "on", "params": {}}
        if any(k in t for k in ("速度", "调速", "转速")):
            speed = _extract_percent(t)
            if speed is not None:
                return {"device": "fan", "action": "set_speed", "params": {"speed": speed}}

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
