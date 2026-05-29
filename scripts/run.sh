#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_DIR}/logs"
PID_FILE="${LOG_DIR}/task1.pid"
PORT="${TASK1_PORT:-8080}"
HOST="${TASK1_HOST:-0.0.0.0}"
RUNTIME_ENV_FILE="${PROJECT_DIR}/config/runtime.env"

# 统一配置文件：若存在则加载（建议将密钥放这里，不要写入脚本）
if [[ -f "${RUNTIME_ENV_FILE}" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${RUNTIME_ENV_FILE}"
  set +a
fi

# =========================
# LLM 配置区（按需修改）
# =========================
# 说明：
# 1) 建议仅在此处维护默认值；临时覆盖可在命令前加环境变量。
# 2) 当前默认按 Kimi(OpenAI 兼容) 配置。
# 3) LLM_API_KEY 需填写你自己的密钥。
: "${LLM_ENABLED:=1}"
: "${LLM_API_URL:=https://api.moonshot.cn/v1/chat/completions}"
: "${LLM_MODEL:=kimi-k2.6}"
: "${LLM_API_KEY:=}"
: "${LLM_TIMEOUT_SECONDS:=45}"
# 留空时由后端按模型自动选择（Kimi K2: thinking=1.0, non-thinking=0.6）
: "${LLM_TEMPERATURE:=}"
# Kimi K2 系列：enabled/disabled，默认关闭思考以降低时延
: "${LLM_THINKING_TYPE:=disabled}"

# 是否前台启动（1=前台实时日志，0=后台 nohup）
: "${RUN_FOREGROUND:=1}"
# 是否打印 /api/wake/status 轮询日志（1=打印，0=默认不打印）
: "${LOG_WAKE_STATUS:=0}"
# 是否打印 POST payload（1=打印，0=默认不打印）
: "${LOG_POST_PAYLOAD:=0}"
# 是否打印 LLM 详细请求/响应内容（1=打印，0=默认不打印）
: "${LOG_LLM_VERBOSE:=0}"

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
PYTHON="${PYTHON:-python3}"
CONDA_DIR="${CONDA_DIR:-/root/miniconda3}"
ENV_NAME="${TASK3_CONDA_ENV:-task3}"
if [[ "${WAKE_USE_CONDA:-1}" == "1" && -x "${CONDA_DIR}/bin/conda" ]]; then
  # shellcheck source=/dev/null
  source "${CONDA_DIR}/etc/profile.d/conda.sh"
  if conda activate "${ENV_NAME}" 2>/dev/null; then
    PYTHON="$(which python3)"
    echo "唤醒/KWS 使用 conda 环境: ${ENV_NAME} (${PYTHON})"
  fi
fi

if [[ "${LLM_ENABLED}" == "1" ]]; then
  echo "LLM 已启用: model=${LLM_MODEL}"
  echo "LLM API: ${LLM_API_URL}"
  if [[ -z "${LLM_API_KEY}" ]]; then
    echo "警告: LLM_ENABLED=1 但 LLM_API_KEY 为空，文本指令走 LLM 时会失败。"
  fi
else
  echo "LLM 未启用（LLM_ENABLED=${LLM_ENABLED}）"
fi

if [[ "${RUN_FOREGROUND}" == "1" ]]; then
  rm -f "${PID_FILE}" || true
  echo "[3/3] 前台启动完成（Ctrl+C 停止）"
  echo "访问地址: http://127.0.0.1:${PORT}"
  echo "日志输出: 终端实时 + ${LOG_DIR}/task1.log"
  TASK1_PORT="${PORT}" TASK1_HOST="${HOST}" \
  LLM_ENABLED="${LLM_ENABLED}" LLM_API_URL="${LLM_API_URL}" LLM_MODEL="${LLM_MODEL}" \
  LLM_API_KEY="${LLM_API_KEY}" LLM_TIMEOUT_SECONDS="${LLM_TIMEOUT_SECONDS}" \
  LLM_TEMPERATURE="${LLM_TEMPERATURE}" LLM_THINKING_TYPE="${LLM_THINKING_TYPE}" \
  LOG_WAKE_STATUS="${LOG_WAKE_STATUS}" \
  LOG_POST_PAYLOAD="${LOG_POST_PAYLOAD}" LOG_LLM_VERBOSE="${LOG_LLM_VERBOSE}" \
  "${PYTHON}" "${PROJECT_DIR}/backend/server.py" 2>&1 | tee -a "${LOG_DIR}/task1.log"
else
  TASK1_PORT="${PORT}" TASK1_HOST="${HOST}" \
  LLM_ENABLED="${LLM_ENABLED}" LLM_API_URL="${LLM_API_URL}" LLM_MODEL="${LLM_MODEL}" \
  LLM_API_KEY="${LLM_API_KEY}" LLM_TIMEOUT_SECONDS="${LLM_TIMEOUT_SECONDS}" \
  LLM_TEMPERATURE="${LLM_TEMPERATURE}" LLM_THINKING_TYPE="${LLM_THINKING_TYPE}" \
  LOG_WAKE_STATUS="${LOG_WAKE_STATUS}" \
  LOG_POST_PAYLOAD="${LOG_POST_PAYLOAD}" LOG_LLM_VERBOSE="${LOG_LLM_VERBOSE}" \
  nohup "${PYTHON}" "${PROJECT_DIR}/backend/server.py" \
    > "${LOG_DIR}/task1.log" 2>&1 &
  NEW_PID=$!
  echo "${NEW_PID}" > "${PID_FILE}"
  echo "[3/3] 后台启动完成"
  echo "访问地址: http://127.0.0.1:${PORT}"
  echo "日志文件: ${LOG_DIR}/task1.log"
  echo "停止命令: ${PROJECT_DIR}/scripts/stop.sh"
fi
