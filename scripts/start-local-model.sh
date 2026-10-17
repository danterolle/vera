#!/usr/bin/env bash
set -euo pipefail

VERA_PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VERA_MODEL_FILE="${VERA_LOCAL_MODEL_FILE:-$VERA_PROJECT_ROOT/.vera/models/Qwen3.5-4B-Q4_K_M.gguf}"
VERA_CUDA_BACKEND="${VERA_LOCAL_BACKEND:-$HOME/.lmstudio/extensions/backends/llama.cpp-linux-x86_64-nvidia-cuda12-avx2-2.56.0}"
VERA_CUDA_VENDOR="${VERA_LOCAL_CUDA_VENDOR:-$HOME/.lmstudio/extensions/backends/vendor/linux-llama-cuda12-vendor-v1}"

if [[ ! -f "$VERA_MODEL_FILE" || ! -x "$VERA_CUDA_BACKEND/llama-server" ]]; then
  echo "Local Qwen3.5 model or LM Studio CUDA runtime is missing. See docs/local-model.md." >&2
  exit 1
fi

exec systemd-run --user --scope --unit=vera-qwen \
  --property=CPUQuota=200% --property=MemoryHigh=6G \
  --property=MemoryMax=8G --property=MemorySwapMax=1G \
  env CUDA_VISIBLE_DEVICES=0 \
  LD_LIBRARY_PATH="$VERA_CUDA_VENDOR:$VERA_CUDA_BACKEND${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$VERA_CUDA_BACKEND/llama-server" \
  --model "$VERA_MODEL_FILE" --alias vera-qwen3.5-4b \
  --host 127.0.0.1 --port 1234 --cors-origins http://127.0.0.1:8000 \
  --device CUDA0 --gpu-layers all --fit off \
  --ctx-size 8192 --parallel 1 --threads 2 --threads-batch 2 \
  --batch-size 128 --ubatch-size 64 --flash-attn on --poll 0 --poll-batch 0 \
  --predict 1024 --reasoning off --reasoning-budget 0 --metrics
