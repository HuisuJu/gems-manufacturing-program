#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROTO_DIR="${ROOT_DIR}/schema/proto"
PC_OUT_DIR="${ROOT_DIR}/pc/proto"
DEVICE_OUT_DIR="${ROOT_DIR}/device/proto"

NANOPB_DIR="${ROOT_DIR}/device/nanopb"
NANOPB_PLUGIN="${NANOPB_DIR}/generator/protoc-gen-nanopb"

PROTOC_ARGS=(
  --experimental_allow_proto3_optional
  -I "${PROTO_DIR}"
)

error() {
  echo "Error: $*" >&2
  exit 1
}

info() {
  echo "$*"
}

# ----------------------------------------------------------------------
# Tool checks
# ----------------------------------------------------------------------

if ! command -v protoc >/dev/null 2>&1; then
  error "'protoc' not found in PATH.

Install it first, for example on Ubuntu:
  sudo apt update
  sudo apt install -y protobuf-compiler"
fi

if [ ! -f "${NANOPB_PLUGIN}" ]; then
  error "nanopb plugin not found:
  ${NANOPB_PLUGIN}

Expected project layout:
  ${ROOT_DIR}/device/nanopb/generator/protoc-gen-nanopb"
fi

if [ ! -x "${NANOPB_PLUGIN}" ]; then
  error "nanopb plugin exists but is not executable:
  ${NANOPB_PLUGIN}

Fix it with:
  chmod +x \"${NANOPB_PLUGIN}\""
fi

if [ ! -d "${PROTO_DIR}" ]; then
  error "proto directory not found:
  ${PROTO_DIR}"
fi

# ----------------------------------------------------------------------
# Output directories
# ----------------------------------------------------------------------

mkdir -p "${PC_OUT_DIR}"
mkdir -p "${DEVICE_OUT_DIR}"

mapfile -t PROTO_FILES < <(find "${PROTO_DIR}" -type f -name "*.proto" | sort)

if [ "${#PROTO_FILES[@]}" -eq 0 ]; then
  error "no .proto files found under:
  ${PROTO_DIR}"
fi

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

info "ROOT_DIR       = ${ROOT_DIR}"
info "PROTO_DIR      = ${PROTO_DIR}"
info "PC_OUT_DIR     = ${PC_OUT_DIR}"
info "DEVICE_OUT_DIR = ${DEVICE_OUT_DIR}"
info "NANOPB_PLUGIN  = ${NANOPB_PLUGIN}"
info "PY_COMPILER    = protoc"
info "C_COMPILER     = protoc --plugin=protoc-gen-nanopb"

info "==> Proto files"
for proto in "${PROTO_FILES[@]}"; do
  rel="${proto#${PROTO_DIR}/}"
  info "  - ${rel}"
done

# ----------------------------------------------------------------------
# Compile Python protobuf files
# ----------------------------------------------------------------------

info "==> Compiling Python protobuf files"
protoc \
  "${PROTOC_ARGS[@]}" \
  --python_out="${PC_OUT_DIR}" \
  "${PROTO_FILES[@]}"

# ----------------------------------------------------------------------
# Compile nanopb files
# ----------------------------------------------------------------------

info "==> Compiling nanopb files"
protoc \
  "${PROTOC_ARGS[@]}" \
  --plugin=protoc-gen-nanopb="${NANOPB_PLUGIN}" \
  --nanopb_out="${DEVICE_OUT_DIR}" \
  "${PROTO_FILES[@]}"

# ----------------------------------------------------------------------
# Ensure Python package directories
# ----------------------------------------------------------------------

info "==> Ensuring Python package directories"
while IFS= read -r -d '' dir; do
  init_file="${dir}/__init__.py"
  if [ ! -f "${init_file}" ]; then
    touch "${init_file}"
  fi
done < <(find "${PC_OUT_DIR}" -type d -print0)

info "Done."