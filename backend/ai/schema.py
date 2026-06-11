from typing import Any, Dict

SUPPORTED_ACTIONS = {
    "fan": {"on", "off", "set_speed"},
    "light": {"on", "off", "set_rgb", "set_brightness"},
    "curtain": {"open", "close", "set_position"},
}


def _ensure_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} 必须是数字")


def normalize_command(command: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(command, dict):
        raise ValueError("command 必须是 JSON 对象")

    device = str(command.get("device", "")).strip().lower()
    action = str(command.get("action", "")).strip().lower()
    params = command.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("params 必须是 JSON 对象")
    if device not in SUPPORTED_ACTIONS:
        raise ValueError("device 不支持")
    if action not in SUPPORTED_ACTIONS[device]:
        raise ValueError(f"{device} action 不支持")

    norm = {"device": device, "action": action, "params": {}}
    if device == "fan" and action == "set_speed":
        norm["params"]["speed"] = _ensure_int(params.get("speed"), "speed")
    elif device == "light" and action == "set_rgb":
        if "r" in params and params["r"] is not None:
            norm["params"]["r"] = _ensure_int(params.get("r"), "r")
        if "g" in params and params["g"] is not None:
            norm["params"]["g"] = _ensure_int(params.get("g"), "g")
        if "b" in params and params["b"] is not None:
            norm["params"]["b"] = _ensure_int(params.get("b"), "b")
        if "brightness" in params and params["brightness"] is not None:
            norm["params"]["brightness"] = _ensure_int(params.get("brightness"), "brightness")
    elif device == "light" and action == "set_brightness":
        norm["params"]["brightness"] = _ensure_int(params.get("brightness"), "brightness")
    elif device == "curtain" and action == "set_position":
        norm["params"]["position"] = _ensure_int(params.get("position"), "position")

    return norm
