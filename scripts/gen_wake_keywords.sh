#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_DIR="${CONDA_DIR:-/root/miniconda3}"
ENV_NAME="${TASK3_CONDA_ENV:-task3}"
if [[ -x "${CONDA_DIR}/bin/conda" ]]; then
  # shellcheck source=/dev/null
  source "${CONDA_DIR}/etc/profile.d/conda.sh"
  conda activate "${ENV_NAME}" 2>/dev/null || true
fi
exec python3 "${ROOT}/scripts/gen_wake_keywords.py"
