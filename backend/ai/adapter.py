import json
import os
import time
from typing import Any, Dict
from urllib import error, request

from ai.schema import normalize_command


def _llm_enabled() -> bool:
    return os.environ.get("LLM_ENABLED", "0") == "1"


def _llm_timeout_seconds() -> float:
    return max(1.0, float(os.environ.get("LLM_TIMEOUT_SECONDS", "8")))


def _resolve_temperature(model: str) -> float:
    # 若用户显式配置了温度，则优先使用该值。
    env_temp = os.environ.get("LLM_TEMPERATURE", "").strip()
    if env_temp:
        return float(env_temp)

    # Kimi K2 系列不同 thinking 模式对温度有固定要求：
    # - thinking=enabled: 1.0
    # - thinking=disabled: 0.6
    if model.startswith("kimi-k2"):
        return 0.6 if _llm_thinking_type() == "disabled" else 1.0

    # 其他模型给一个保守默认值。
    return 0.7


def _llm_thinking_type() -> str:
    return os.environ.get("LLM_THINKING_TYPE", "").strip().lower()


def _log_llm_verbose() -> bool:
    return os.environ.get("LOG_LLM_VERBOSE", "0") == "1"


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        raise ValueError("LLM 返回为空")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM 返回中未找到 JSON 对象")
    return json.loads(text[start : end + 1])


def _truncate(text: str, limit: int = 800) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


def _build_prompt(text: str, state: Dict[str, Any]) -> str:
    return (
        "你是设备控制指令解析器。"
        "请把用户输入解析为 JSON，字段仅允许 device/action/params/need_confirm/reason。"
        "device 仅可为 fan/light/curtain；"
        "fan action: on/off/set_speed；"
        "light action: on/off/set_rgb/set_brightness；"
        "curtain action: open/close/set_position。"
        "不要输出 markdown。"
        f"\n当前状态: {json.dumps(state, ensure_ascii=False)}"
        f"\n用户输入: {text}"
    )


def _call_llm_api(prompt: str) -> Dict[str, Any]:
    api_url = os.environ.get("LLM_API_URL", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip() or "gpt-4o-mini"
    temperature = _resolve_temperature(model)
    if not api_url:
        raise RuntimeError("缺少 LLM_API_URL")
    if not api_key:
        raise RuntimeError("缺少 LLM_API_KEY")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是设备控制指令解析器。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    # Kimi K2 系列支持 thinking 参数；默认关闭以降低时延。
    thinking_type = _llm_thinking_type()
    if thinking_type and model.startswith("kimi-k2"):
        payload["thinking"] = {"type": thinking_type}
    if _log_llm_verbose():
        print(
            "[project] LLM POST "
            f"url={api_url} model={model} timeout={_llm_timeout_seconds()} temperature={temperature} "
            f"payload={_truncate(json.dumps(payload, ensure_ascii=False))}"
        )
    else:
        print(
            "[project] LLM POST "
            f"url={api_url} model={model} timeout={_llm_timeout_seconds()} temperature={temperature}"
        )
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(api_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    started_at = time.time()
    try:
        with request.urlopen(req, timeout=_llm_timeout_seconds()) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        elapsed_ms = int((time.time() - started_at) * 1000)
        print(f"[project] LLM HTTPError elapsed_ms={elapsed_ms} status={exc.code} detail={_truncate(detail)}")
        raise RuntimeError(f"LLM 请求失败: {exc.code} {detail}") from exc
    except Exception as exc:
        elapsed_ms = int((time.time() - started_at) * 1000)
        print(f"[project] LLM Exception elapsed_ms={elapsed_ms} error={repr(exc)}")
        raise RuntimeError(f"LLM 请求失败: {exc}") from exc

    elapsed_ms = int((time.time() - started_at) * 1000)
    print(f"[project] LLM OK elapsed_ms={elapsed_ms}")
    if _log_llm_verbose():
        print(f"[project] LLM RESP raw={_truncate(raw)}")
    data = json.loads(raw)
    content = data["choices"][0]["message"]["content"]
    parsed = _extract_json_object(content)
    parsed["_model"] = model
    parsed["_elapsed_ms"] = elapsed_ms
    return parsed


def parse_text_to_command(text: str, state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text 不能为空")

    if not _llm_enabled():
        return {
            "ok": False,
            "source": "llm",
            "command": None,
            "meta": {"mode": "llm", "reason": "llm_disabled"},
        }

    prompt = _build_prompt(text=text, state=state)
    parsed = _call_llm_api(prompt)
    command = normalize_command(parsed)
    return {
        "ok": True,
        "source": "llm",
        "command": command,
        "meta": {
            "mode": "llm",
            "reason": parsed.get("reason", ""),
            "need_confirm": bool(parsed.get("need_confirm", False)),
            "model": parsed.get("_model"),
            "llm_elapsed_ms": parsed.get("_elapsed_ms"),
        },
    }
