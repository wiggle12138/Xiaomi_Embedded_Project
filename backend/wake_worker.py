"""唤醒状态：命中唤醒词后，更新状态并触发扬声器回复。"""

import os
import threading
import time
from typing import Callable, Optional

from project_config import get_wake_greeting_text, get_wake_idle_message, get_wake_keyword_text
from wake_engine import SherpaWakeEngine

_lock = threading.Lock()
_state = {
    "state": "idle",
    "message": get_wake_idle_message(),
    "greeting": None,
    "wake_enabled": False,
    "cooldown_until": 0.0,
}
_engine: Optional[SherpaWakeEngine] = None
_speak_fn: Optional[Callable[[], None]] = None
_busy = False


def set_speak_fn(fn: Callable[[], None]):
    global _speak_fn
    _speak_fn = fn


def _display_seconds() -> float:
    return max(1.0, float(os.environ.get("WAKE_GREETING_SECONDS", "5")))


def _cooldown_seconds() -> float:
    return max(0.0, float(os.environ.get("WAKE_COOLDOWN_SECONDS", "3")))


def snapshot() -> dict:
    with _lock:
        data = dict(_state)
    data["wake_keyword_text"] = get_wake_keyword_text()
    if _engine:
        data["kws_ready"] = _engine.ready
        data["kws_listening"] = _engine.is_running()
        if _engine.last_error:
            data["kws_error"] = _engine.last_error
    else:
        data["kws_ready"] = False
        data["kws_listening"] = False
    return data


def _on_wake():
    global _busy
    with _lock:
        if _busy or _state["state"] == "awake":
            return
        if time.time() < _state.get("cooldown_until", 0):
            return
        _busy = True
    threading.Thread(target=_handle_wake, daemon=True).start()


def _handle_wake():
    global _busy
    try:
        if _engine:
            _engine.pause()
        greeting = get_wake_greeting_text()
        with _lock:
            _state.update(state="awake", message=greeting, greeting=greeting)
        print(f"[project] 唤醒命中，回复占位: {greeting}")

        if _speak_fn:
            try:
                _speak_fn()
            except Exception as exc:
                print(f"[project] 扬声器回复失败: {exc}")

        time.sleep(_display_seconds())
        with _lock:
            _state.update(
                state="idle",
                message=get_wake_idle_message(),
                greeting=None,
                cooldown_until=time.time() + _cooldown_seconds(),
            )
    finally:
        if _engine:
            _engine.resume()
        _busy = False


def try_start() -> bool:
    """WAKE_ENABLED=1 时尝试启动；失败不阻断 Project 主服务。"""
    if os.environ.get("WAKE_ENABLED", "1") != "1":
        print("[project] 唤醒已关闭 (WAKE_ENABLED=0)")
        return False
    global _engine
    _engine = SherpaWakeEngine(on_wake=_on_wake)
    if not _engine.load():
        print(f"[project] 唤醒未启动: {_engine.last_error}")
        return False
    try:
        _engine.start()
        with _lock:
            _state["wake_enabled"] = True
            _state["message"] = get_wake_idle_message()
        print(f"[project] 流式唤醒已启动，等待「{get_wake_keyword_text()}」")
        return True
    except Exception as exc:
        print(f"[project] 唤醒启动失败: {exc}")
        return False


def stop():
    global _engine
    if _engine:
        _engine.stop()
    with _lock:
        _state["wake_enabled"] = False
