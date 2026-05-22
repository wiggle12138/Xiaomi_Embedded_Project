#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${PROJECT_DIR}/logs/audio-check"
mkdir -p "${OUT_DIR}"

DURATION="${1:-5}"
RATE="${S3_RATE:-16000}"
CHANNELS="${S3_CHANNELS:-1}"
ALSA_DEVICE="${S3_DEVICE:-default}"
TINYCAP_CARD="${S3_CARD:-0}"
TINYCAP_DEVICE="${S3_PCM_DEVICE:-0}"
OUT_FILE="${OUT_DIR}/s3_$(date +%Y%m%d_%H%M%S).wav"

echo "===== S3 语音输入自检 ====="
echo "[1/4] 声卡/录音能力检查:"
if command -v arecord >/dev/null 2>&1; then
  arecord -l || true
fi
if command -v tinycap >/dev/null 2>&1; then
  echo "检测到 tinycap，可按 S3 demo 路径录音。"
fi
echo
echo "[2/4] 录音参数:"
echo "  alsa_device=${ALSA_DEVICE}"
echo "  tinycap_card=${TINYCAP_CARD}, tinycap_pcm_device=${TINYCAP_DEVICE}"
echo "  rate=${RATE}"
echo "  channels=${CHANNELS}"
echo "  duration=${DURATION}s"
echo "  output=${OUT_FILE}"
echo

echo "[3/4] 开始录音..."
if command -v tinycap >/dev/null 2>&1; then
  tinycap "${OUT_FILE}" -D "${TINYCAP_CARD}" -d "${TINYCAP_DEVICE}" -t "${DURATION}" -b 16 -r "${RATE}"
elif command -v arecord >/dev/null 2>&1; then
  arecord -D "${ALSA_DEVICE}" -f S16_LE -r "${RATE}" -c "${CHANNELS}" -d "${DURATION}" "${OUT_FILE}"
else
  echo "未找到 tinycap 或 arecord，无法录音。"
  echo "建议："
  echo "  1) 若是 S3 官方环境，确认 tinycap 可用；"
  echo "  2) 或安装 alsa-utils 后使用 arecord。"
  exit 1
fi
echo "录音完成。"
echo

echo "[4/4] 文件信息:"
ls -lh "${OUT_FILE}"

if command -v aplay >/dev/null 2>&1; then
  echo
  echo "准备回放录音..."
  aplay "${OUT_FILE}" || true
fi

echo
echo "S3 自检结束。"
