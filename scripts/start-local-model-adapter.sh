#!/usr/bin/env bash
set -euo pipefail

VERA_PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

# Use the base model and converted step-400 adapter documented in docs/local-model.md.
export VERA_LOCAL_MODEL_FILE="${VERA_LOCAL_MODEL_FILE:-$VERA_PROJECT_ROOT/.vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf}"
export VERA_LOCAL_LORA_FILE="${VERA_LOCAL_LORA_FILE:-$VERA_PROJECT_ROOT/.vera/finetuning/adapter-step400/vera-step400-lora-f16.gguf}"
export VERA_LOCAL_MODEL_ALIAS="${VERA_LOCAL_MODEL_ALIAS:-vera-qwen3.5-4b-step400}"

exec bash "$VERA_PROJECT_ROOT/scripts/start-local-model.sh"
