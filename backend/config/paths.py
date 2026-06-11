"""Project 目录与静态资源路径。"""

from pathlib import Path

# backend/ 的上一级为 Project 根目录
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
BIN_DIR = ROOT_DIR / "bin"
AUDIO_DIR = ROOT_DIR / "logs" / "audio-check"
