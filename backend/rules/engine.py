"""规则引擎：设备状态轮询 + 手动触发。"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from rules.schema import TRIGGER_TYPES, validate_actions

ENGINE_LOCK = threading.Lock()
ENGINE_THREAD: Optional[threading.Thread] = None
ENGINE_STOP = threading.Event()
LAST_FIRED: Dict[str, float] = {}
RECENT_RUNS: List[Dict[str, Any]] = []
MAX_RECENT_RUNS = 50

_execute_action: Optional[Callable[..., Dict[str, Any]]] = None
_snapshot_state: Optional[Callable[[], Dict[str, Any]]] = None
POLL_INTERVAL_SECONDS = 5.0


def configure(*, execute_action: Callable[..., Dict[str, Any]], snapshot_state: Callable[[], Dict[str, Any]]) -> None:
    global _execute_action, _snapshot_state
    _execute_action = execute_action
    _snapshot_state = snapshot_state


def _compare(left: Any, operator: str, right: Any) -> bool:
    if operator == "eq":
        return left == right
    if operator == "ne":
        return left != right
    if operator == "gt":
        return left > right
    if operator == "gte":
        return left >= right
    if operator == "lt":
        return left < right
    if operator == "lte":
        return left <= right
    return False


def _state_field_value(state: Dict[str, Any], device: str, field: str) -> Any:
    block = state.get(device, {})
    if field not in block:
        raise ValueError(f"状态字段不存在: {device}.{field}")
    return block[field]


def evaluate_device_state_trigger(trigger: Dict[str, Any], state: Dict[str, Any]) -> bool:
    device = trigger.get("device")
    field = trigger.get("field")
    operator = trigger.get("operator")
    expected = trigger.get("value")
    actual = _state_field_value(state, device, field)
    return _compare(actual, operator, expected)


def is_trigger_implemented(trigger: Dict[str, Any]) -> bool:
    trigger_type = trigger.get("type", "")
    meta = TRIGGER_TYPES.get(trigger_type, {})
    return bool(meta.get("implemented"))


def evaluate_trigger(trigger: Dict[str, Any], state: Dict[str, Any]) -> bool:
    trigger_type = trigger.get("type")
    if trigger_type == "manual":
        return False
    if trigger_type == "device_state":
        return evaluate_device_state_trigger(trigger, state)
    return False


def _in_cooldown(rule: Dict[str, Any]) -> bool:
    rule_id = rule.get("id", "")
    cooldown = int((rule.get("options") or {}).get("cooldown_seconds", 30))
    last = LAST_FIRED.get(rule_id, 0.0)
    return (time.time() - last) < max(0, cooldown)


def _record_run(rule_id: str, source: str, ok: bool, message: str, actions: Optional[List[Dict[str, Any]]] = None) -> None:
    entry = {
        "rule_id": rule_id,
        "source": source,
        "ok": ok,
        "message": message,
        "ts": time.time(),
        "actions": actions or [],
    }
    RECENT_RUNS.insert(0, entry)
    if len(RECENT_RUNS) > MAX_RECENT_RUNS:
        del RECENT_RUNS[MAX_RECENT_RUNS:]


def execute_rule_actions(rule: Dict[str, Any], *, source: str = "rule") -> Dict[str, Any]:
    if _execute_action is None:
        raise RuntimeError("规则引擎未配置 execute_action")
    actions = validate_actions(rule.get("actions", []))
    messages = []
    last_result = None
    for action in actions:
        last_result = _execute_action(action, source=source)
        messages.append(last_result.get("message", "ok"))
    message = "；".join(messages)
    return {
        "rule_id": rule.get("id"),
        "message": message,
        "actions": actions,
        "result": last_result,
    }


def run_rule(rule: Dict[str, Any], *, source: str = "manual", force: bool = False) -> Dict[str, Any]:
    from rules import store as rules_store

    rule_id = rule.get("id", "")
    trigger = rule.get("trigger") or {}
    if source != "manual" and not rule.get("enabled"):
        return {"skipped": True, "message": "规则未启用"}
    if source == "auto" and not is_trigger_implemented(trigger):
        return {"skipped": True, "message": "触发源未实现"}
    if not force and _in_cooldown(rule):
        return {"skipped": True, "message": "冷却中，跳过执行"}

    try:
        result = execute_rule_actions(rule, source="rule" if source == "auto" else "manual")
        LAST_FIRED[rule_id] = time.time()
        rules_store.mark_rule_run(rule_id, status="ok", message=result["message"])
        _record_run(rule_id, source, True, result["message"], result.get("actions"))
        result["skipped"] = False
        return result
    except Exception as exc:
        msg = str(exc)
        rules_store.mark_rule_run(rule_id, status="error", message=msg)
        _record_run(rule_id, source, False, msg)
        raise


def run_rule_by_id(rule_id: str) -> Dict[str, Any]:
    from rules import store as rules_store

    rule = rules_store.get_rule(rule_id)
    if not rule:
        raise ValueError("规则不存在")
    return run_rule(rule, source="manual", force=True)


def evaluate_all(rules: List[Dict[str, Any]], state: Dict[str, Any]) -> None:
    for rule in rules:
        if not rule.get("enabled"):
            continue
        trigger = rule.get("trigger") or {}
        if not is_trigger_implemented(trigger):
            continue
        try:
            if evaluate_trigger(trigger, state):
                run_rule(rule, source="auto")
        except Exception as exc:
            print(f"[rules] auto run failed rule={rule.get('id')} error={exc}")


def _engine_loop() -> None:
    from rules import store as rules_store

    while not ENGINE_STOP.is_set():
        try:
            if _snapshot_state is not None:
                state = _snapshot_state()
                evaluate_all(rules_store.list_rules(), state)
        except Exception as exc:
            print(f"[rules] engine loop error: {exc}")
        ENGINE_STOP.wait(POLL_INTERVAL_SECONDS)


def start() -> None:
    global ENGINE_THREAD
    with ENGINE_LOCK:
        if ENGINE_THREAD and ENGINE_THREAD.is_alive():
            return
        ENGINE_STOP.clear()
        ENGINE_THREAD = threading.Thread(target=_engine_loop, daemon=True, name="rules-engine")
        ENGINE_THREAD.start()
        print("[rules] engine started")


def stop() -> None:
    ENGINE_STOP.set()


def recent_runs(limit: int = 20) -> List[Dict[str, Any]]:
    return RECENT_RUNS[: max(1, min(limit, MAX_RECENT_RUNS))]
