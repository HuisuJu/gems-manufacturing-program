#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROTO_DIR="${ROOT_DIR}/proto"
PC_OUT_DIR="${ROOT_DIR}/pc/src/proto"
DEVICE_OUT_DIR="${ROOT_DIR}/device/src/proto"

USE_GRPC_TOOLS=0
if ! command -v protoc >/dev/null 2>&1; then
  USE_GRPC_TOOLS=1
fi

if ! command -v protoc-gen-nanopb >/dev/null 2>&1; then
  echo "Error: protoc-gen-nanopb not found in PATH"
  exit 1
fi

echo "ROOT_DIR       = ${ROOT_DIR}"
echo "PROTO_DIR      = ${PROTO_DIR}"
echo "PC_OUT_DIR     = ${PC_OUT_DIR}"
echo "DEVICE_OUT_DIR = ${DEVICE_OUT_DIR}"
echo "PY_COMPILER    = $([ "${USE_GRPC_TOOLS}" -eq 1 ] && echo 'python -m grpc_tools.protoc' || echo 'protoc')"
echo "C_COMPILER     = protoc --nanopb_out"

mkdir -p "${PC_OUT_DIR}"
mkdir -p "${DEVICE_OUT_DIR}"

compile_proto() {
  local proto_file="$1"
  local rel_dir="$2"
  local base_name

  base_name="$(basename "${proto_file}")"

  local pc_out="${PC_OUT_DIR}/${rel_dir}"
  local device_out="${DEVICE_OUT_DIR}/${rel_dir}"

  mkdir -p "${pc_out}"
  mkdir -p "${device_out}"

  echo "==> Compiling: ${proto_file}"
  echo "    relative dir: ${rel_dir}"
  echo "    python out  : ${pc_out}"
  echo "    nanopb out  : ${device_out}"

  if [ "${USE_GRPC_TOOLS}" -eq 1 ]; then
    python -m grpc_tools.protoc \
      -I "${PROTO_DIR}" \
      --python_out="${PC_OUT_DIR}" \
      "${proto_file}"
  else
    protoc \
      -I "${PROTO_DIR}" \
      --python_out="${PC_OUT_DIR}" \
      "${proto_file}"
  fi

  protoc \
    -I "${PROTO_DIR}" \
    --nanopb_out="${DEVICE_OUT_DIR}" \
    "${proto_file}"
}

echo "==> Compiling common proto files"
shopt -s nullglob
for proto in "${PROTO_DIR}"/*.proto; do
  compile_proto "${proto}" ""
done

echo "==> Compiling model-specific proto files"
for model_dir in "${PROTO_DIR}"/*/; do
  [ -d "${model_dir}" ] || continue

  model_name="$(basename "${model_dir}")"

  for proto in "${model_dir}"/*.proto; do
    [ -f "${proto}" ] || continue
    compile_proto "${proto}" "${model_name}"
  done
done

echo "Done."