#!/usr/bin/env python3
"""生成 Project 唤醒词 keywords.txt，默认：小爱同学"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from wake_engine import find_model_dir  # noqa: E402


def ensure_deps():
    try:
        import pypinyin  # noqa: F401
        import sentencepiece  # noqa: F401
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "pypinyin", "sentencepiece"])


def main():
    model_dir = find_model_dir()
    if not model_dir:
        print("未找到模型，请解压到 Project/models 或 task3/models", file=sys.stderr)
        sys.exit(1)

    keyword = os.environ.get("WAKE_KEYWORD_TEXT", "芮鑫龙")
    ensure_deps()
    from sherpa_onnx import text2token

    score = os.environ.get("WAKE_KEYWORDS_SCORE", "2.0")
    threshold = os.environ.get("WAKE_KEYWORDS_THRESHOLD", "0.25")
    encoded = text2token([keyword], tokens=str(model_dir / "tokens.txt"), tokens_type="ppinyin")
    parts = list(encoded[0]) + [f":{score}", f"#{threshold}", f"@{keyword}"]
    out_dir = ROOT / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "keywords.txt"
    line = " ".join(parts)
    out.write_text(line + "\n", encoding="utf-8")
    print(f"已写入 {out}\n{line}")


if __name__ == "__main__":
    main()
