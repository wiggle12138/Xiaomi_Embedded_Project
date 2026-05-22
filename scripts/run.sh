#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_DIR}/logs"
PID_FILE="${LOG_DIR}/task1.pid"
PORT="${TASK1_PORT:-8080}"
HOST="${TASK1_HOST:-0.0.0.0}"

mkdir -p "${LOG_DIR}"

echo "[1/3] 编译本地控制程序..."
make -C "${PROJECT_DIR}/native"

if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}" || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "${OLD_PID}" 2>/dev/null; then
    echo "检测到旧服务正在运行(PID=${OLD_PID})，先停止..."
    kill "${OLD_PID}" || true
    sleep 1
  fi
fi

echo "[2/3] 启动后端服务..."
TASK1_PORT="${PORT}" TASK1_HOST="${HOST}" nohup python3 "${PROJECT_DIR}/backend/server.py" \
  > "${LOG_DIR}/task1.log" 2>&1 &
NEW_PID=$!
echo "${NEW_PID}" > "${PID_FILE}"

echo "[3/3] 启动完成"
echo "访问地址: http://127.0.0.1:${PORT}"
echo "日志文件: ${LOG_DIR}/task1.log"
echo "停止命令: ${PROJECT_DIR}/scripts/stop.sh"
