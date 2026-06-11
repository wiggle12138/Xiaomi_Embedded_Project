import os

DEFAULT_WAKE_KEYWORD_TEXT = "小龙同学"
DEFAULT_WAKE_GREETING_TEXT = "你好呀"


def get_wake_keyword_text() -> str:
    value = os.environ.get("WAKE_KEYWORD_TEXT", DEFAULT_WAKE_KEYWORD_TEXT).strip()
    return value or DEFAULT_WAKE_KEYWORD_TEXT


def get_wake_idle_message() -> str:
    return f"等待唤醒词「{get_wake_keyword_text()}」…"


def get_wake_greeting_text() -> str:
    value = os.environ.get("WAKE_GREETING_TEXT", DEFAULT_WAKE_GREETING_TEXT).strip()
    return value or DEFAULT_WAKE_GREETING_TEXT
