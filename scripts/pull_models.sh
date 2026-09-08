#!/bin/bash
set -euo pipefail
# Pull modelos 32B offline a volumen Docker 'models' (requiere internet + huggingface-cli)
# Uso: bash scripts/pull_models.sh
MODELS_DIR=${MODELS_DIR:-./models}
mkdir -p "$MODELS_DIR"
echo "Pull Qwen2.5-VL-32B-AWQ (~18GB)..."
huggingface-cli download Qwen/Qwen2.5-VL-32B-Instruct-AWQ --local-dir "$MODELS_DIR/Qwen2.5-VL-32B-Instruct-AWQ" --local-dir-use-symlinks False || echo "Descarga manual: huggingface-cli no encontrado, usa: pip install huggingface_hub"
echo "Pull Qwen2.5-32B-AWQ (~20GB)..."
huggingface-cli download Qwen/Qwen2.5-32B-Instruct-AWQ --local-dir "$MODELS_DIR/Qwen2.5-32B-Instruct-AWQ" --local-dir-use-symlinks False || true
echo "Pull bge-m3 (~2.2GB)..."
huggingface-cli download BAAI/bge-m3 --local-dir "$MODELS_DIR/bge-m3" --local-dir-use-symlinks False || true
echo "Whisper large-v3-turbo se descarga automáticamente en primer run de contenedor whisper"
echo "Listo. Copia a volumen Docker: docker run --rm -v cu002-local_models:/models -v $PWD/models:/src alpine cp -r /src/* /models/"
