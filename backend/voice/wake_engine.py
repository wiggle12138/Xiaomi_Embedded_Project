"""流式 KWS（sherpa-onnx + arecord），复用 task3 模型目录。"""

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from config.paths import ROOT_DIR

SAMPLE_RATE = 16000
CHUNK_SAMPLES = int(0.1 * SAMPLE_RATE)


def find_model_dir() -> Optional[Path]:
    candidates = []
    env_dir = os.environ.get("WAKE_MODEL_DIR", "").strip()
    if env_dir:
        candidates.append(Path(env_dir))

    for models_root in (ROOT_DIR / "models", ROOT_DIR.parent / "task3" / "models"):
        if not models_root.is_dir():
            continue
        for child in sorted(models_root.iterdir()):
            if child.is_dir():
                candidates.append(child)
        if (models_root / "tokens.txt").is_file():
            candidates.insert(0, models_root)

    for base in candidates:
        if not base.is_dir():
            continue
        if (base / "tokens.txt").is_file() and list(base.glob("encoder*.onnx")):
            return base
    return None


def resolve_model_paths(model_dir: Path) -> dict:
    kw_env = os.environ.get("WAKE_KEYWORDS_FILE", "").strip()
    project_kw = ROOT_DIR / "models" / "keywords.txt"
    if kw_env:
        keywords = Path(kw_env)
    elif project_kw.is_file():
        keywords = project_kw
    else:
        keywords = model_dir / "keywords.txt"
    return {
        "tokens": str(model_dir / "tokens.txt"),
        "encoder": str(sorted(model_dir.glob("encoder*.onnx"))[0]),
        "decoder": str(sorted(model_dir.glob("decoder*.onnx"))[0]),
        "joiner": str(sorted(model_dir.glob("joiner*.onnx"))[0]),
        "keywords_file": str(keywords),
    }


class SherpaWakeEngine:
    def __init__(self, on_wake: Callable[[], None]):
        self.on_wake = on_wake
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._spotter = None
        self._model_dir: Optional[Path] = None
        self._ready = False
        self._last_error = ""

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def last_error(self) -> str:
        return self._last_error

    def load(self) -> bool:
        try:
            import numpy as np  # noqa: F401
        except ImportError:
            self._last_error = "缺少 numpy（建议 conda activate task3）"
            return False
        try:
            import sherpa_onnx  # noqa: F401
        except ImportError:
            self._last_error = "缺少 sherpa-onnx（建议 conda activate task3）"
            return False

        self._model_dir = find_model_dir()
        if not self._model_dir:
            self._last_error = "未找到 KWS 模型（Project/models 或 task3/models）"
            return False

        paths = resolve_model_paths(self._model_dir)
        if not Path(paths["keywords_file"]).is_file():
            self._last_error = f"缺少 {paths['keywords_file']}，请运行 scripts/gen_wake_keywords.sh"
            return False

        try:
            import sherpa_onnx

            self._spotter = sherpa_onnx.KeywordSpotter(
                tokens=paths["tokens"],
                encoder=paths["encoder"],
                decoder=paths["decoder"],
                joiner=paths["joiner"],
                keywords_file=paths["keywords_file"],
                num_threads=int(os.environ.get("WAKE_NUM_THREADS", "2")),
                keywords_score=float(os.environ.get("WAKE_KEYWORDS_SCORE", "2.0")),
                keywords_threshold=float(os.environ.get("WAKE_KEYWORDS_THRESHOLD", "0.25")),
                provider="cpu",
            )
        except Exception as exc:
            self._last_error = f"加载 KWS 失败: {exc}"
            return False

        self._ready = True
        self._last_error = ""
        return True

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if not self._ready and not self.load():
            raise RuntimeError(self._last_error or "KWS 未就绪")
        if self.is_running():
            return
        self._stop.clear()
        self._pause.clear()
        self._thread = threading.Thread(target=self._loop, name="project-kws", daemon=True)
        self._thread.start()
        time.sleep(0.3)
        if not self.is_running():
            raise RuntimeError(self._last_error or "KWS 线程启动失败")

    def stop(self):
        self._stop.set()
        self._pause.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def pause(self):
        self._pause.set()

    def resume(self):
        self._pause.clear()

    def _capture_device(self) -> str:
        if os.environ.get("S3_DEVICE", "").strip():
            return os.environ["S3_DEVICE"].strip()
        return f"hw:{os.environ.get('S3_CARD', '0')},{os.environ.get('S3_PCM_DEVICE', '0')}"

    def _loop(self):
        import numpy as np

        byte_len = CHUNK_SAMPLES * 2
        while not self._stop.is_set():
            if self._pause.is_set():
                time.sleep(0.1)
                continue
            proc = None
            try:
                proc = subprocess.Popen(
                    [
                        "arecord",
                        "-D",
                        self._capture_device(),
                        "-f",
                        "S16_LE",
                        "-r",
                        str(SAMPLE_RATE),
                        "-c",
                        "1",
                        "-q",
                        "-",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                stream = self._spotter.create_stream()
                while not self._stop.is_set() and not self._pause.is_set():
                    raw = proc.stdout.read(byte_len)
                    if not raw or len(raw) < byte_len:
                        break
                    samples = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
                    stream.accept_waveform(SAMPLE_RATE, samples)
                    while self._spotter.is_ready(stream):
                        self._spotter.decode_stream(stream)
                        if self._spotter.get_result(stream):
                            self._spotter.reset_stream(stream)
                            if proc.poll() is None:
                                proc.terminate()
                                proc.wait(timeout=2)
                            self.on_wake()
                            break
            except Exception as exc:
                self._last_error = str(exc)
                print(f"[project] KWS 异常: {exc}")
                time.sleep(1)
            finally:
                if proc and proc.poll() is None:
                    proc.terminate()
