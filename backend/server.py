#!/usr/bin/env python3
"""Project HTTP 入口：路由编排与服务启动。"""

import json
import mimetypes
import os
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ai import adapter as ai_adapter
from ai.schema import normalize_command
from config.paths import FRONTEND_DIR, ROOT_DIR
from device.actions import execute_action, parse_text_to_action, snapshot_state
from device.probe import device_snapshot
from rules import engine as rules_engine
from rules import schema as rule_schema
from rules import store as rules_store
from voice import wake_worker
from voice.audio_io import (
    latest_audio_file,
    playback_audio,
    record_audio,
    speak_wake_reply,
    start_voice_session,
    stop_voice_session,
    voice_snapshot,
)

HOST = os.environ.get("TASK1_HOST", "0.0.0.0")
PORT = int(os.environ.get("TASK1_PORT", "8080"))


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip().lower()
        return v in ("1", "true", "yes", "on", "open", "开启", "打开")
    return bool(value)


def _enrich_rules(items):
    return [rule_schema.enrich_rule(item) for item in items]


def _dispatch_rules_api(method, path, payload=None):
    """规则 REST 路由。"""
    parts = [p for p in path.split("/") if p]
    if len(parts) == 2 and parts[0] == "api" and parts[1] == "rules":
        if method == "GET":
            return {"rules": _enrich_rules(rules_store.list_rules())}
        if method == "POST":
            return rule_schema.enrich_rule(rules_store.create_rule(payload or {}))
        raise ValueError("方法不支持")

    if len(parts) == 3 and parts[0] == "api" and parts[1] == "rules" and parts[2] == "meta":
        if method == "GET":
            return rule_schema.build_meta(device_snapshot())
        raise ValueError("方法不支持")

    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "rules":
        rule_id = parts[2]
        action = parts[3] if len(parts) >= 4 else None
        if action is None:
            if method == "GET":
                rule = rules_store.get_rule(rule_id)
                if not rule:
                    raise ValueError("规则不存在")
                return rule_schema.enrich_rule(rule)
            if method == "PUT":
                return rule_schema.enrich_rule(rules_store.update_rule(rule_id, payload or {}))
            if method == "DELETE":
                rules_store.delete_rule(rule_id)
                return {"deleted": rule_id}
            raise ValueError("方法不支持")
        if action == "toggle" and method == "POST":
            enabled = payload.get("enabled") if isinstance(payload, dict) else None
            if enabled is None:
                rule = rules_store.get_rule(rule_id)
                if not rule:
                    raise ValueError("规则不存在")
                enabled = not bool(rule.get("enabled"))
            return rule_schema.enrich_rule(rules_store.set_rule_enabled(rule_id, bool(enabled)))
        if action == "run" and method == "POST":
            return rules_engine.run_rule_by_id(rule_id)
        raise ValueError("接口不存在")

    raise ValueError("接口不存在")


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
            self._send_json(200, {"ok": True, "data": snapshot_state()})
            return
        if path == "/api/devices":
            self._send_json(200, {"ok": True, "data": device_snapshot()})
            return
        if path == "/api/voice/latest":
            latest = latest_audio_file()
            self._send_json(200, {"ok": True, "data": {"audio_file": str(latest) if latest else None}})
            return
        if path == "/api/voice/status":
            self._send_json(200, {"ok": True, "data": voice_snapshot()})
            return
        if path == "/api/wake/status":
            self._send_json(200, {"ok": True, "data": wake_worker.snapshot()})
            return
        if path == "/api/rules" or path.startswith("/api/rules/"):
            try:
                result = _dispatch_rules_api("GET", path)
                self._send_json(200, {"ok": True, "data": result})
            except ValueError as exc:
                self._send_json(400 if "不存在" in str(exc) else 404, {"ok": False, "error": str(exc)})
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
        if path.startswith("/js/"):
            target = (FRONTEND_DIR / path.lstrip("/")).resolve()
            if str(target).startswith(str(FRONTEND_DIR.resolve())):
                self._serve_file(target)
                return

        self.send_error(404, "Not Found")

    def do_POST(self):
        path = urlparse(self.path).path
        started_at = time.time()
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "JSON 格式错误"})
            return
        if os.environ.get("LOG_POST_PAYLOAD", "0") == "1":
            print(f"[project] POST {path} payload={json.dumps(payload, ensure_ascii=False)}")
        else:
            print(f"[project] POST {path}")

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
            elif path == "/api/ai/route":
                text = payload.get("text", "")
                state = snapshot_state()
                try:
                    action = parse_text_to_action(text, state=state)
                    result = {
                        "source": "route",
                        "message": "direct",
                        "route": {
                            "mode": "direct",
                            "action": normalize_command(action),
                        },
                    }
                except ValueError:
                    result = {
                        "source": "route",
                        "message": "llm",
                        "route": {"mode": "llm"},
                    }
            elif path == "/api/ai/command":
                if isinstance(payload.get("command"), dict):
                    action = normalize_command(payload["command"])
                    result = execute_action(action, source="structured")
                else:
                    text = payload.get("text", "")
                    state = snapshot_state()
                    try:
                        action = parse_text_to_action(text, state=state)
                        result = execute_action(action, source="text_direct")
                        result["nlp"] = {"mode": "direct"}
                    except ValueError as direct_err:
                        parsed = ai_adapter.parse_text_to_command(text=text, state=state)
                        if parsed["ok"]:
                            result = execute_action(parsed["command"], source=parsed["source"])
                            result["nlp"] = parsed["meta"]
                        else:
                            raise ValueError(f"直接指令不匹配({direct_err})，且 LLM 未可用")
                    result["text"] = text
            elif path == "/api/voice/record":
                seconds = payload.get("seconds", 3)
                rate = payload.get("rate", 16000)
                file_path = record_audio(seconds=seconds, rate=rate)
                result = {
                    "source": "voice",
                    "message": "录音完成",
                    "audio_file": str(file_path),
                    "state": snapshot_state(),
                }
            elif path == "/api/voice/start":
                max_seconds = payload.get("max_seconds", 60)
                rate = payload.get("rate", 16000)
                file_path = start_voice_session(max_seconds=max_seconds, rate=rate)
                result = {
                    "source": "voice",
                    "message": "录音已开始",
                    "audio_file": str(file_path),
                    "voice_status": voice_snapshot(),
                    "state": snapshot_state(),
                }
            elif path == "/api/voice/stop":
                file_path, duration = stop_voice_session()
                result = {
                    "source": "voice",
                    "message": f"录音已停止，时长 {duration:.1f}s",
                    "audio_file": str(file_path),
                    "duration_seconds": round(duration, 1),
                    "voice_status": voice_snapshot(),
                    "state": snapshot_state(),
                }
                transcript = str(payload.get("mock_text", "")).strip()
                if transcript:
                    action = parse_text_to_action(transcript, state=snapshot_state())
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
                    "state": snapshot_state(),
                }
            elif path == "/api/voice/command":
                seconds = payload.get("seconds", 3)
                rate = payload.get("rate", 16000)
                file_path = record_audio(seconds=seconds, rate=rate)

                transcript = str(payload.get("mock_text", "")).strip()
                if not transcript:
                    raise ValueError("当前为语音链路第一版，请传入 mock_text 作为识别文本")

                action = parse_text_to_action(transcript, state=snapshot_state())
                result = execute_action(action, source="voice")
                result["audio_file"] = str(file_path)
                result["transcript"] = transcript
            elif path == "/api/rules" or (path.startswith("/api/rules/") and path.endswith(("/toggle", "/run"))):
                result = _dispatch_rules_api("POST", path, payload)
            else:
                self._send_json(404, {"ok": False, "error": "接口不存在"})
                return
            elapsed_ms = int((time.time() - started_at) * 1000)
            print(f"[project] POST {path} ok elapsed_ms={elapsed_ms}")
            self._send_json(
                200,
                {
                    "ok": True,
                    "data": result,
                    "message": result.get("message", "ok") if isinstance(result, dict) else "ok",
                },
            )
        except ValueError as exc:
            elapsed_ms = int((time.time() - started_at) * 1000)
            print(f"[project] POST {path} bad_request elapsed_ms={elapsed_ms} error={exc}")
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            elapsed_ms = int((time.time() - started_at) * 1000)
            print(f"[project] POST {path} failed elapsed_ms={elapsed_ms} error={exc!r}")
            print(traceback.format_exc())
            self._send_json(500, {"ok": False, "error": str(exc)})

    def do_PUT(self):
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "JSON 格式错误"})
            return
        print(f"[project] PUT {path}")
        try:
            if path.startswith("/api/rules/"):
                result = _dispatch_rules_api("PUT", path, payload)
                self._send_json(200, {"ok": True, "data": result})
                return
            self._send_json(404, {"ok": False, "error": "接口不存在"})
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            print(traceback.format_exc())
            self._send_json(500, {"ok": False, "error": str(exc)})

    def do_DELETE(self):
        path = urlparse(self.path).path
        print(f"[project] DELETE {path}")
        try:
            if path.startswith("/api/rules/"):
                result = _dispatch_rules_api("DELETE", path)
                self._send_json(200, {"ok": True, "data": result})
                return
            self._send_json(404, {"ok": False, "error": "接口不存在"})
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            print(traceback.format_exc())
            self._send_json(500, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        message = fmt % args
        if "GET /api/wake/status" in message and os.environ.get("LOG_WAKE_STATUS", "0") != "1":
            return
        print("[project]", message)


def main():
    rules_store.configure(ROOT_DIR / "data" / "rules.json")
    rules_engine.configure(execute_action=execute_action, snapshot_state=snapshot_state)
    rules_engine.start()
    wake_worker.set_speak_fn(speak_wake_reply)
    wake_worker.try_start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"project server listening on http://{HOST}:{PORT}")
    print(f"frontend root: {FRONTEND_DIR}")
    server.serve_forever()


if __name__ == "__main__":
    main()
