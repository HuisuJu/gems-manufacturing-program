#!/usr/bin/env bash
set -euo pipefail

# repo root 기준으로 동작하도록
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODEL_DIR="${ROOT_DIR}/model"
OUT_BASE="${ROOT_DIR}/src/model"

# protoc 존재 여부 확인 (없으면 grpc_tools 사용)
USE_GRPC_TOOLS=0
if ! command -v protoc >/dev/null 2>&1; then
  USE_GRPC_TOOLS=1
fi

mkdir -p "${OUT_BASE}"

# src/model 및 각 모델 폴더를 패키지로 만들고 싶으면 __init__.py 생성(선택)
touch "${OUT_BASE}/__init__.py"

shopt -s nullglob
for proto in "${MODEL_DIR}"/*/factory_data.proto; do
  model_name="$(basename "$(dirname "${proto}")")"
  out_dir="${OUT_BASE}/${model_name}"
  mkdir -p "${out_dir}"
  touch "${out_dir}/__init__.py"

  echo "==> [${model_name}] ${proto} -> ${out_dir}"

  if [ "${USE_GRPC_TOOLS}" -eq 1 ]; then
    # grpcio-tools 필요: pip install grpcio-tools
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