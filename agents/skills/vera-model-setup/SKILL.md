---
name: vera-model-setup
description: >-
  Use this skill when setting up, testing, or troubleshooting the local LLM runtime (Qwen 3.5 4B, LM Studio,
  Bionic, llama-server) and configuring OpenAI-compatible endpoints for VERA.
---

# VERA Local Model Setup Skill

This skill documents how to configure, start, and verify the local language model runtime required for VERA's generation and reasoning stages.

---

## 1. Supported Model Profiles

VERA is designed and benchmarked against small, highly-capable local models:

| Platform | Recommended Model Profile | Quantization | Server Option |
| :--- | :--- | :--- | :--- |
| **Linux / NVIDIA (~6GB VRAM)** | `Qwen3.5-4B-GGUF` | `Q4_K_M` | LM Studio GUI or `scripts/start-local-model.sh` |
| **Apple Silicon (M1/M2/M3/M4)** | `Qwen3.5-4B-MTP-GGUF` | `Q6_K` (MTP draft) | `llama-server` (MTP enabled) |
| **CPU / Fallback** | Deterministic Engine | N/A | Built-in (`VERA_LLM_PROVIDER=deterministic`) |

---

## 2. Starting the Model Server (Port 1234)

Choose one of the following methods:

### Method A: Linux Headless Script
If running on Linux with NVIDIA drivers and LM Studio runtime installed:
```bash
bash scripts/start-local-model.sh
```
- Serves model as `vera-qwen3.5-4b` on `http://127.0.0.1:1234`.
- Runs under cgroup memory and CPU limits (2 logical cores, 8GB RAM).

### Method B: LM Studio / Bionic GUI
1. Open LM Studio / Bionic.
2. Load `Qwen3.5-4B-Q4_K_M.gguf`.
3. In Developer/Local Server settings:
   - Port: `1234`
   - Context Length: `8192` tokens
   - GPU Offload: Maximum layers
   - Disable Thinking / reasoning mode if available
4. Start the server.

---

## 3. Verifying Endpoint & Model ID

Run a curl query against the model server:
```bash
curl -fsS http://127.0.0.1:1234/v1/models
```

Identify the exact `id` field in the response (e.g. `vera-qwen3.5-4b` or `qwen3.5-4b`).

Update `.env`:
```dotenv
VERA_LLM_PROVIDER=openai
VERA_LLM_MODEL=vera-qwen3.5-4b
VERA_LLM_BASE_URL=http://127.0.0.1:1234/v1
VERA_LLM_RESPONSE_FORMAT=json_schema
VERA_LLM_TIMEOUT_SECONDS=120
VERA_LLM_MAX_OUTPUT_TOKENS=1024
```

---

## 4. End-to-End Verification with VERA

Test that VERA communicates with the model and successfully generates cited claims:

```bash
# 1. Execute an analysis query
uv run --extra knowledge-graph vera analyze "Explain PowerShell with one sourced claim." --offline --json
```

### Verification Checks:
1. Check `metadata.model`: It must match your configured Qwen model ID.
2. Check `metadata.provider_fallback`: Must be `false`. If `true`, the local model server timed out or returned an error, and VERA fell back to deterministic summaries.
3. Check `claims`: Ensure the output contains structured claims with citations.
