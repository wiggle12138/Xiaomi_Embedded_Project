"""规则持久化（JSON 文件）。"""

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rule_schema import validate_rule_payload

RULES_LOCK = threading.Lock()
RULES_FILE: Optional[Path] = None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def configure(rules_file: Path) -> None:
    global RULES_FILE
    RULES_FILE = Path(rules_file)
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not RULES_FILE.exists():
        _write_unlocked({"rules": _default_rules()})


def _default_rules() -> List[Dict[str, Any]]:
    now = _now_iso()
    return [
        {
            "id": "rule_demo_gesture",
            "name": "手势六关闭床头灯",
            "description": "摄像头识别手势「六」时关灯",
            "enabled": False,
            "trigger": {"type": "camera_gesture", "gesture": "六"},
            "actions": [{"device": "light", "action": "off", "params": {}}],
            "options": {"cooldown_seconds": 30},
            "created_at": now,
            "updated_at": now,
            "last_run_at": None,
            "last_run_status": "pending",
            "last_run_message": "触发源待接入",
        },
        {
            "id": "rule_demo_temperature",
            "name": "温度高于26度打开床头灯",
            "description": "温度传感器高于 26 时开灯",
            "enabled": False,
            "trigger": {"type": "temperature", "operator": "gt", "value": 26},
            "actions": [{"device": "light", "action": "on", "params": {}}],
            "options": {"cooldown_seconds": 30},
            "created_at": now,
            "updated_at": now,
            "last_run_at": None,
            "last_run_status": "pending",
            "last_run_message": "触发源待接入",
        },
        {
            "id": "rule_demo_brightness",
            "name": "光照低于50打开床头灯",
            "description": "光照传感器低于 50 时开灯",
            "enabled": False,
            "trigger": {"type": "brightness_sensor", "operator": "lt", "value": 50},
            "actions": [{"device": "light", "action": "on", "params": {}}],
            "options": {"cooldown_seconds": 30},
            "created_at": now,
            "updated_at": now,
            "last_run_at": None,
            "last_run_status": "pending",
            "last_run_message": "触发源待接入",
        },
        {
            "id": "rule_demo_curtain_light",
            "name": "窗帘关小后自动开灯",
            "description": "窗帘开度低于 20 时自动开灯",
            "enabled": False,
            "trigger": {
                "type": "device_state",
                "device": "curtain",
                "field": "position",
                "operator": "lt",
                "value": 20,
            },
            "actions": [{"device": "light", "action": "on", "params": {}}],
            "options": {"cooldown_seconds": 30},
            "created_at": now,
            "updated_at": now,
            "last_run_at": None,
            "last_run_status": "idle",
            "last_run_message": "",
        },
    ]


def _read_unlocked() -> Dict[str, Any]:
    if RULES_FILE is None:
        raise RuntimeError("rules_store 未初始化")
    raw = RULES_FILE.read_text(encoding="utf-8")
    data = json.loads(raw) if raw.strip() else {"rules": []}
    if not isinstance(data.get("rules"), list):
        data["rules"] = []
    return data


def _write_unlocked(data: Dict[str, Any]) -> None:
    if RULES_FILE is None:
        raise RuntimeError("rules_store 未初始化")
    RULES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_rules() -> List[Dict[str, Any]]:
    with RULES_LOCK:
        return list(_read_unlocked().get("rules", []))


def get_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    with RULES_LOCK:
        for rule in _read_unlocked().get("rules", []):
            if rule.get("id") == rule_id:
                return dict(rule)
    return None


def create_rule(payload: Dict[str, Any]) -> Dict[str, Any]:
    norm = validate_rule_payload(payload, require_name=True)
    if "trigger" not in norm or "actions" not in norm:
        raise ValueError("创建规则需要 trigger 与 actions")
    now = _now_iso()
    rule = {
        "id": f"rule_{uuid.uuid4().hex[:10]}",
        "name": norm["name"],
        "description": norm.get("description", ""),
        "enabled": norm.get("enabled", True),
        "trigger": norm["trigger"],
        "actions": norm["actions"],
        "options": norm.get("options", {"cooldown_seconds": 30}),
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
        "last_run_status": "idle",
        "last_run_message": "",
    }
    with RULES_LOCK:
        data = _read_unlocked()
        data["rules"].append(rule)
        _write_unlocked(data)
    return dict(rule)


def update_rule(rule_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    norm = validate_rule_payload(payload, require_name=False)
    with RULES_LOCK:
        data = _read_unlocked()
        for idx, rule in enumerate(data["rules"]):
            if rule.get("id") != rule_id:
                continue
            updated = dict(rule)
            for key in ("name", "description", "enabled", "trigger", "actions", "options"):
                if key in norm:
                    updated[key] = norm[key]
            updated["updated_at"] = _now_iso()
            data["rules"][idx] = updated
            _write_unlocked(data)
            return dict(updated)
    raise ValueError("规则不存在")


def delete_rule(rule_id: str) -> None:
    with RULES_LOCK:
        data = _read_unlocked()
        new_rules = [r for r in data["rules"] if r.get("id") != rule_id]
        if len(new_rules) == len(data["rules"]):
            raise ValueError("规则不存在")
        data["rules"] = new_rules
        _write_unlocked(data)


def set_rule_enabled(rule_id: str, enabled: bool) -> Dict[str, Any]:
    return update_rule(rule_id, {"enabled": bool(enabled)})


def mark_rule_run(rule_id: str, *, status: str, message: str) -> None:
    with RULES_LOCK:
        data = _read_unlocked()
        for idx, rule in enumerate(data["rules"]):
            if rule.get("id") != rule_id:
                continue
            rule = dict(rule)
            rule["last_run_at"] = _now_iso()
            rule["last_run_status"] = status
            rule["last_run_message"] = message
            rule["updated_at"] = _now_iso()
            data["rules"][idx] = rule
            _write_unlocked(data)
            return
