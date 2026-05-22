#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PID_FILE="${PROJECT_DIR}/logs/task1.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "未找到 PID 文件，服务可能未启动。"
  exit 0
fi

PID="$(cat "${PID_FILE}" || true)"
if [[ -z "${PID}" ]]; then
  echo "PID 文件为空。"
  rm -f "${PID_FILE}"
  exit 0
fi

if kill -0 "${PID}" 2>/dev/null; then
  kill "${PID}"
  echo "已停止服务，PID=${PID}"
else
  echo "进程不存在，清理 PID 文件。"
fi

rm -f "${PID_FILE}"
