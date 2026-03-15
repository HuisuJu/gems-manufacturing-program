#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PC_DIR="${REPO_ROOT}/pc"

# You can override these from the shell:
#   PYTHON_BIN=python3.13 tools/package_pc.sh
#   VENV_DIR=.venv-packaging tools/package_pc.sh
PYTHON_BIN="${PYTHON_BIN:-python3.13}"
VENV_DIR_NAME="${VENV_DIR:-.venv-packaging}"
VENV_DIR="${PC_DIR}/${VENV_DIR_NAME}"

log() {
    printf '[PACKAGE] %s\n' "$*"
}

fail() {
    printf '[PACKAGE][ERROR] %s\n' "$*" >&2
    exit 1
}

require_dir() {
    local path="$1"
    [[ -d "${path}" ]] || fail "Directory not found: ${path}"
}

require_file() {
    local path="$1"
    [[ -f "${path}" ]] || fail "File not found: ${path}"
}

log "Repository root: ${REPO_ROOT}"
log "PC directory: ${PC_DIR}"

require_dir "${PC_DIR}"
require_dir "${REPO_ROOT}/schema/json"
require_file "${PC_DIR}/main.spec"
require_file "${PC_DIR}/requirements.txt"
require_file "${PC_DIR}/src/main.py"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    fail "Python executable not found: ${PYTHON_BIN}"
fi

log "Using Python: ${PYTHON_BIN}"

if [[ ! -d "${VENV_DIR}" ]]; then
    log "Creating virtual environment: ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
else
    log "Reusing virtual environment: ${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

log "Upgrading packaging tools"
python -m pip install --upgrade pip setuptools wheel

log "Installing project requirements"
python -m pip install -r "${PC_DIR}/requirements.txt"

log "Installing PyInstaller"
python -m pip install --upgrade pyinstaller

log "Checking NumPy package metadata"
python - <<'PY'
import importlib.metadata as m
version = m.version("numpy")
if not isinstance(version, str) or not version.strip():
    raise SystemExit("NumPy metadata is invalid.")
print(f"[PACKAGE] NumPy version: {version}")
PY

log "Cleaning previous build outputs"
rm -rf "${PC_DIR}/build" "${PC_DIR}/dist"

log "Running PyInstaller"
(
    cd "${PC_DIR}"
    pyinstaller --clean main.spec
)

log "Build completed"
log "Output directory: ${PC_DIR}/dist"
