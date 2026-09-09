#!/usr/bin/env sh
set -eu

MODEL_DIR="${MODEL_DIR:-/models}"

if ! command -v huggingface-cli >/dev/null 2>&1; then
  echo "huggingface-cli is required. Install it with: pip install huggingface-hub" >&2
  exit 1
fi

mkdir -p "$MODEL_DIR"

huggingface-cli download Qwen/Qwen2.5-VL-32B-Instruct-AWQ \
  --local-dir "$MODEL_DIR/Qwen2.5-VL-32B-Instruct-AWQ"

huggingface-cli download Qwen/Qwen2.5-32B-Instruct-AWQ \
  --local-dir "$MODEL_DIR/Qwen2.5-32B-Instruct-AWQ"
