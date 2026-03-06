#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODEL_DIR="${ROOT_DIR}/model"
OUT_MODEL_DIR="${ROOT_DIR}/src/model"

USE_GRPC_TOOLS=0
if ! command -v protoc >/dev/null 2>&1; then
  USE_GRPC_TOOLS=1
fi

echo "ROOT_DIR      = ${ROOT_DIR}"
echo "MODEL_DIR     = ${MODEL_DIR}"
echo "OUT_MODEL_DIR = ${OUT_MODEL_DIR}"
echo "COMPILER      = $([ "${USE_GRPC_TOOLS}" -eq 1 ] && echo 'python -m grpc_tools.protoc' || echo 'protoc')"

mkdir -p "${OUT_MODEL_DIR}"

shopt -s nullglob
for proto in "${MODEL_DIR}"/*/factory_data.proto; do
  model_name="$(basename "$(dirname "${proto}")")"
  out_dir="${OUT_MODEL_DIR}/${model_name}"

  mkdir -p "${out_dir}"

  echo "==> [${model_name}] ${proto}"
  if [ "${USE_GRPC_TOOLS}" -eq 1 ]; then
    python -m grpc_tools.protoc \
      -I "${MODEL_DIR}/${model_name}" \
      --python_out="${out_dir}" \
      "${proto}"
  else
    protoc \
      -I "${MODEL_DIR}/${model_name}" \
      --python_out="${out_dir}" \
      "${proto}"
  fi
done

echo "Done."