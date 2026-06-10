"""规则结构校验与元数据定义。"""

from typing import Any, Dict, List, Optional

from ai_schema import SUPPORTED_ACTIONS, normalize_command

# 触发类型：implemented 表示引擎 V1 是否已接入
TRIGGER_TYPES = {
    "manual": {
        "label": "手动测试",
        "source_device": None,
        "implemented": True,
        "hint": "仅通过「测试运行」手动触发",
    },
    "device_state": {
        "label": "设备状态",
        "source_device": None,
        "implemented": True,
        "hint": "根据灯/风扇/窗帘当前状态自动触发",
    },
    "key": {
        "label": "按键输入",
        "source_device": "S1",
        "implemented": False,
        "hint": "触发源待接入（S1 按键事件）",
    },
    "camera_gesture": {
        "label": "摄像头手势",
        "source_device": "S4",
        "implemented": False,
        "hint": "触发源待接入（S4 视觉识别）",
    },
    "voice_wake": {
        "label": "语音唤醒",
        "source_device": "S3",
        "implemented": False,
        "hint": "触发源待接入（唤醒词事件）",
    },
    "temperature": {
        "label": "温度传感器",
        "source_device": "S8",
        "implemented": False,
        "hint": "触发源待接入（温度子板）",
    },
    "brightness_sensor": {
        "label": "光照传感器",
        "source_device": "S2",
        "implemented": False,
        "hint": "触发源待接入（光照子板）",
    },
    "motion": {
        "label": "人体感应",
        "source_device": "S7",
        "implemented": False,
        "hint": "触发源待接入（人体红外）",
    },
}

STATE_DEVICES = {
    "fan": {
        "label": "风扇 E2",
        "board": "E2",
        "fields": {
            "on": {"label": "开关", "type": "bool"},
            "speed": {"label": "速度", "type": "number", "min": 0, "max": 100},
        },
    },
    "light": {
        "label": "灯光 E1",
        "board": "E1",
        "fields": {
            "on": {"label": "开关", "type": "bool"},
            "brightness": {"label": "亮度", "type": "number", "min": 0, "max": 100},
            "r": {"label": "红色", "type": "number", "min": 0, "max": 255},
            "g": {"label": "绿色", "type": "number", "min": 0, "max": 255},
            "b": {"label": "蓝色", "type": "number", "min": 0, "max": 255},
        },
    },
    "curtain": {
        "label": "窗帘 E3",
        "board": "E3",
        "fields": {
            "position": {"label": "开度", "type": "number", "min": 0, "max": 100},
        },
    },
}

OPERATORS = {
    "eq": "等于",
    "ne": "不等于",
    "gt": "大于",
    "gte": "大于等于",
    "lt": "小于",
    "lte": "小于等于",
}

ACTION_LABELS = {
    ("fan", "on"): "开启风扇",
    ("fan", "off"): "关闭风扇",
    ("fan", "set_speed"): "设置风速",
    ("light", "on"): "开灯",
    ("light", "off"): "关灯",
    ("light", "set_rgb"): "设置颜色",
    ("light", "set_brightness"): "设置亮度",
    ("curtain", "open"): "窗帘全开",
    ("curtain", "close"): "窗帘全关",
    ("curtain", "set_position"): "设置开度",
}

EXEC_DEVICE_BOARDS = {"fan": "E2", "light": "E1", "curtain": "E3"}


def _ensure_str(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} 不能为空")
    return text


def _ensure_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(value, (int, float)):
        return value != 0
    return default


def _ensure_int(value: Any, field: str, min_value: Optional[int] = None, max_value: Optional[int] = None) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} 必须是整数")
    if min_value is not None and num < min_value:
        raise ValueError(f"{field} 不能小于 {min_value}")
    if max_value is not None and num > max_value:
        raise ValueError(f"{field} 不能大于 {max_value}")
    return num


def validate_trigger(trigger: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(trigger, dict):
        raise ValueError("trigger 必须是 JSON 对象")
    trigger_type = _ensure_str(trigger.get("type"), "trigger.type")
    if trigger_type not in TRIGGER_TYPES:
        raise ValueError("trigger.type 不支持")

    norm = {"type": trigger_type}
    if trigger_type == "manual":
        return norm

    if trigger_type == "device_state":
        device = _ensure_str(trigger.get("device"), "trigger.device").lower()
        if device not in STATE_DEVICES:
            raise ValueError("trigger.device 不支持")
        field = _ensure_str(trigger.get("field"), "trigger.field")
        fields = STATE_DEVICES[device]["fields"]
        if field not in fields:
            raise ValueError("trigger.field 不支持")
        operator = _ensure_str(trigger.get("operator"), "trigger.operator")
        if operator not in OPERATORS:
            raise ValueError("trigger.operator 不支持")
        field_type = fields[field]["type"]
        if field_type == "bool":
            value = _ensure_bool(trigger.get("value"))
        else:
            value = _ensure_int(
                trigger.get("value"),
                "trigger.value",
                fields[field].get("min"),
                fields[field].get("max"),
            )
        norm.update({"device": device, "field": field, "operator": operator, "value": value})
        return norm

    if trigger_type == "key":
        norm["key_code"] = _ensure_str(trigger.get("key_code", "any"), "trigger.key_code")
        return norm

    if trigger_type == "camera_gesture":
        norm["gesture"] = _ensure_str(trigger.get("gesture"), "trigger.gesture")
        return norm

    if trigger_type == "voice_wake":
        norm["keyword"] = _ensure_str(trigger.get("keyword", ""), "trigger.keyword") if trigger.get("keyword") else ""
        return norm

    if trigger_type in ("temperature", "brightness_sensor", "motion"):
        operator = _ensure_str(trigger.get("operator"), "trigger.operator")
        if operator not in OPERATORS:
            raise ValueError("trigger.operator 不支持")
        norm["operator"] = operator
        norm["value"] = _ensure_int(trigger.get("value"), "trigger.value")
        return norm

    raise ValueError("trigger 校验失败")


def validate_actions(actions: Any) -> List[Dict[str, Any]]:
    if not isinstance(actions, list) or not actions:
        raise ValueError("actions 至少包含 1 个动作")
    normalized = []
    for idx, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"actions[{idx}] 必须是 JSON 对象")
        normalized.append(normalize_command(action))
    return normalized


def validate_rule_payload(payload: Dict[str, Any], *, require_name: bool = True) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("规则 body 必须是 JSON 对象")
    norm = {}
    if "name" in payload or require_name:
        norm["name"] = _ensure_str(payload.get("name"), "name")
    if "description" in payload:
        norm["description"] = str(payload.get("description") or "").strip()
    if "enabled" in payload:
        norm["enabled"] = _ensure_bool(payload.get("enabled"))
    if "trigger" in payload:
        norm["trigger"] = validate_trigger(payload["trigger"])
    if "actions" in payload:
        norm["actions"] = validate_actions(payload["actions"])
    if "options" in payload:
        options = payload["options"]
        if not isinstance(options, dict):
            raise ValueError("options 必须是 JSON 对象")
        cooldown = options.get("cooldown_seconds", 30)
        norm["options"] = {"cooldown_seconds": _ensure_int(cooldown, "options.cooldown_seconds", 0, 3600)}
    return norm


def trigger_summary(trigger: Dict[str, Any]) -> str:
    trigger_type = trigger.get("type", "")
    meta = TRIGGER_TYPES.get(trigger_type, {})
    label = meta.get("label", trigger_type)
    if trigger_type == "manual":
        return f"触发块：{label}（手动）"
    if trigger_type == "device_state":
        device = STATE_DEVICES.get(trigger.get("device", ""), {}).get("label", trigger.get("device", ""))
        field = trigger.get("field", "")
        op = OPERATORS.get(trigger.get("operator", ""), trigger.get("operator", ""))
        return f"触发条件：{device} {field} {op} {trigger.get('value')}"
    if trigger_type == "camera_gesture":
        return f"触发条件：手势识别为「{trigger.get('gesture', '-')}」"
    if trigger_type == "key":
        return f"触发条件：按键 {trigger.get('key_code', 'any')}"
    if trigger_type in ("temperature", "brightness_sensor", "motion"):
        op = OPERATORS.get(trigger.get("operator", ""), trigger.get("operator", ""))
        return f"触发条件：{label} {op} {trigger.get('value')}"
    return f"触发块：{label}"


def actions_summary(actions: List[Dict[str, Any]]) -> str:
    parts = []
    for action in actions:
        device = action.get("device", "")
        act = action.get("action", "")
        label = ACTION_LABELS.get((device, act), f"{device}.{act}")
        params = action.get("params") or {}
        if params:
            parts.append(f"{label} {params}")
        else:
            parts.append(label)
    return "执行动作：" + " → ".join(parts)


def enrich_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(rule)
    trigger = item.get("trigger") or {}
    trigger_type = trigger.get("type", "")
    meta = TRIGGER_TYPES.get(trigger_type, {})
    item["trigger_summary"] = trigger_summary(trigger)
    item["actions_summary"] = actions_summary(item.get("actions") or [])
    item["trigger_implemented"] = bool(meta.get("implemented"))
    item["trigger_hint"] = meta.get("hint", "")
    return item


def build_meta(device_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    online_boards = set()
    for item in device_snapshot.get("devices", []):
        if item.get("online"):
            online_boards.add(item.get("device_id"))

    triggers = []
    for trigger_type, meta in TRIGGER_TYPES.items():
        board = meta.get("source_device")
        available = True if not board else board in online_boards
        triggers.append(
            {
                "type": trigger_type,
                "label": meta["label"],
                "source_device": board,
                "implemented": meta["implemented"],
                "available": available,
                "hint": meta["hint"],
            }
        )

    actions = []
    for device, action_set in SUPPORTED_ACTIONS.items():
        board = EXEC_DEVICE_BOARDS.get(device)
        available = board in online_boards if board else False
        for action in sorted(action_set):
            actions.append(
                {
                    "device": device,
                    "action": action,
                    "label": ACTION_LABELS.get((device, action), f"{device}.{action}"),
                    "board": board,
                    "available": available,
                }
            )

    state_devices = []
    for device_id, info in STATE_DEVICES.items():
        board = info["board"]
        state_devices.append(
            {
                "device": device_id,
                "label": info["label"],
                "board": board,
                "available": board in online_boards,
                "fields": info["fields"],
            }
        )

    return {
        "triggers": triggers,
        "actions": actions,
        "state_devices": state_devices,
        "operators": [{"id": k, "label": v} for k, v in OPERATORS.items()],
    }
