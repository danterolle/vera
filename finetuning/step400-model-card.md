---
base_model: Qwen/Qwen3.5-4B
library_name: peft
tags:
  - vera
  - lora
  - qwen3.5
  - experimental
---

# VERA Qwen3.5-4B step-400 adapter

Experimental, publicly released LoRA adapter for drafting VERA-compatible,
evidence-grounded answers. Base-model weights and training/evaluation datasets are
not included.

## Provenance

- Base: `Qwen/Qwen3.5-4B`, revision
  `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`
- Adapter: LoRA rank 8, alpha 16, dropout 0, seven projection modules
- Training: FP32, 400 optimizer updates, approximately 0.81 epoch
- Training prompt: the pre-v3 historical answer contract
- Data: synthetic and not expert-reviewed

The later English-only v3 evaluations used mechanically aligned prompts without
retraining this adapter. The v3 candidate preserves the existing targets and is not
authorized for training. Public release of this adapter does not authorize training
on the dataset or production deployment.

## Local validation

A four-case offline A/B smoke check through VERA used the same Q6_K base model with
the LoRA disabled/enabled, ReAct disabled, live sources disabled, and temporary
databases. It used only repository-bundled corpus snapshots, the current system prompt
(`sha256 010be6a57f95bfbb34e27478cc496576b5ca72c5e3d4c35ddd6393a8b18272c7`),
English output, and a 4,096-token output limit. Under the permissive status/citation
criterion, the base passed 2/4 cases and the adapter 3/4. Requiring zero validation
errors gives the stricter result of 2/4 for both; the adapter's missing-CVE case had
one validation error. Both models classified the PowerShell question as out of scope.
The adapter gave a concise grounded CWE-89 answer and marked the missing CVE
unavailable; the base summary included a contradictory XSS statement for CWE-89 and
combined an unavailable CVE result with a supported-fact claim. Both handled the
recipe question as out of scope.

This is a small runtime smoke check, not a factual-accuracy benchmark or deployment
approval. The runtime citation validator does not validate every sentence in the
summary.

Reproduce the download, checksum verification, server startup, and local A/B test from
a VERA source checkout:

```bash
uv sync --extra knowledge-graph
uv run --extra knowledge-graph --with huggingface_hub \
  python scripts/reproduce_step400.py
```

The script downloads the base GGUF and tested adapter GGUF at pinned revisions,
verifies their SHA-256 digests, starts a loopback server, compares LoRA scales 0 and
1, then stops the server. It uses repository-bundled evidence, disables ReAct and live
sources, and writes analysis state only to temporary SQLite databases. A compatible
`llama-server` built from commit `8642541b2` must already be installed; native server
builds remain platform-specific.

## Files and checksums

The artifact contains `adapter_config.json`, `adapter_model.safetensors`, and the
tested `vera-step400-lora-f16.gguf` conversion. Their SHA-256 digests are recorded in
`step400-adapter.sha256`. No dataset, runtime database, credential or base-model
weight is included.

## Serving

Use the pinned base model under its own license terms. The repository includes both
the PEFT adapter and the tested F16 GGUF conversion. Applying the LoRA to a quantized
GGUF differs numerically from merging before quantization; validate the served model
and retain VERA's human-review gate.
