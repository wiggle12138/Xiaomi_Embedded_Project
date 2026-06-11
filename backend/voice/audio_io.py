"""S3 录音、E4 回放、按住说话会话。"""

import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from config.paths import AUDIO_DIR, ROOT_DIR
from config.util import clamp
from device.runtime import mark_device_error, mark_device_success

AUDIO_LOCK = threading.Lock()
VOICE_SESSION_LOCK = threading.Lock()
VOICE_SESSION = {
    "active": False,
    "proc": None,
    "audio_file": None,
    "start_ts": 0.0,
    "max_seconds": 0,
    "rate": 16000,
}


def _safe_audio_seconds(value):
    return clamp(int(value), 1, 10)


def record_audio(seconds=3, rate=16000):
    seconds = _safe_audio_seconds(seconds)
    rate = clamp(int(rate), 8000, 48000)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUDIO_DIR / f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

    tinycap_card = os.environ.get("S3_CARD", "0")
    tinycap_device = os.environ.get("S3_PCM_DEVICE", "0")
    alsa_device = os.environ.get("S3_DEVICE", "default")

    if not shutil.which("tinycap") and not shutil.which("arecord"):
        raise RuntimeError("未找到 tinycap/arecord，无法录音")

    with AUDIO_LOCK:
        if shutil.which("tinycap"):
            cmd = [
                "tinycap",
                str(out_path),
                "-D",
                str(tinycap_card),
                "-d",
                str(tinycap_device),
                "-t",
                str(seconds),
                "-b",
                "16",
                "-r",
                str(rate),
            ]
        else:
            cmd = [
                "arecord",
                "-D",
                str(alsa_device),
                "-f",
                "S16_LE",
                "-r",
                str(rate),
                "-c",
                "1",
                "-d",
                str(seconds),
                str(out_path),
            ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds + 5)

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "录音失败"
        mark_device_error("S3", err)
        raise RuntimeError(err)
    mark_device_success("S3")
    return out_path


def playback_audio(audio_path):
    path = Path(audio_path)
    if not path.exists():
        raise ValueError(f"音频文件不存在: {path}")
    if not shutil.which("tinyplay") and not shutil.which("aplay"):
        raise RuntimeError("未找到 tinyplay/aplay，无法回放")

    tinyplay_card = os.environ.get("E4_CARD", "0")
    tinyplay_device = os.environ.get("E4_PCM_DEVICE", "1")
    rate = os.environ.get("E4_RATE", "16000")

    with AUDIO_LOCK:
        if shutil.which("tinyplay"):
            cmd = [
                "tinyplay",
                "-D",
                str(tinyplay_card),
                "-d",
                str(tinyplay_device),
                "-r",
                str(rate),
                str(path),
            ]
        else:
            cmd = ["aplay", str(path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "回放失败"
        mark_device_error("E4", err)
        raise RuntimeError(err)
    mark_device_success("E4")
    return True


def speak_wake_reply():
    """扬声器回复：播放 assets/speech/reply.wav。"""
    wav = os.environ.get("WAKE_REPLY_WAV", str(ROOT_DIR / "assets/speech/reply.wav"))
    path = Path(wav)
    if not path.is_file():
        print(f"[project] 未找到回复音频 {path}，请将 reply.wav 放入 assets/speech/")
        return
    playback_audio(path)


def latest_audio_file():
    if not AUDIO_DIR.exists():
        return None
    files = sorted([p for p in AUDIO_DIR.glob("*.wav") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def voice_snapshot():
    with VOICE_SESSION_LOCK:
        active = VOICE_SESSION["active"]
        start_ts = VOICE_SESSION["start_ts"]
        max_seconds = VOICE_SESSION["max_seconds"]
        audio_file = VOICE_SESSION["audio_file"]
    elapsed = max(0, int(time.time() - start_ts)) if active and start_ts > 0 else 0
    remaining = max(0, max_seconds - elapsed) if active else 0
    return {
        "active": active,
        "audio_file": str(audio_file) if audio_file else None,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "max_seconds": max_seconds,
    }


def _voice_auto_stop_worker():
    while True:
        with VOICE_SESSION_LOCK:
            if not VOICE_SESSION["active"]:
                return
            proc = VOICE_SESSION["proc"]
            start_ts = VOICE_SESSION["start_ts"]
            max_seconds = VOICE_SESSION["max_seconds"]
        if time.time() - start_ts >= max_seconds:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
            with VOICE_SESSION_LOCK:
                VOICE_SESSION["active"] = False
                VOICE_SESSION["proc"] = None
            return
        time.sleep(0.2)


def start_voice_session(max_seconds=60, rate=16000):
    max_seconds = clamp(int(max_seconds), 1, 60)
    rate = clamp(int(rate), 8000, 48000)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUDIO_DIR / f"voice_hold_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

    if not shutil.which("arecord"):
        raise RuntimeError("按住说话模式需要 arecord，请先安装 alsa-utils")
    alsa_device = os.environ.get("S3_DEVICE", "default")
    cmd = [
        "arecord",
        "-D",
        str(alsa_device),
        "-f",
        "S16_LE",
        "-r",
        str(rate),
        "-c",
        "1",
        str(out_path),
    ]

    with VOICE_SESSION_LOCK:
        if VOICE_SESSION["active"]:
            raise ValueError("已有录音会话在进行中")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        VOICE_SESSION["active"] = True
        VOICE_SESSION["proc"] = proc
        VOICE_SESSION["audio_file"] = out_path
        VOICE_SESSION["start_ts"] = time.time()
        VOICE_SESSION["max_seconds"] = max_seconds
        VOICE_SESSION["rate"] = rate

    mark_device_success("S3")
    threading.Thread(target=_voice_auto_stop_worker, daemon=True).start()
    return out_path


def stop_voice_session():
    with VOICE_SESSION_LOCK:
        if not VOICE_SESSION["active"]:
            raise ValueError("当前没有正在进行的录音会话")
        proc = VOICE_SESSION["proc"]
        out_path = VOICE_SESSION["audio_file"]
        start_ts = VOICE_SESSION["start_ts"]
        VOICE_SESSION["active"] = False
        VOICE_SESSION["proc"] = None

    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)

    duration = max(0.0, time.time() - start_ts)
    if not out_path or not Path(out_path).exists():
        raise RuntimeError("录音文件未生成，请重试")
    mark_device_success("S3")
    return Path(out_path), duration
