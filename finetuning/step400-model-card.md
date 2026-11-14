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

This publicly released LoRA adapter drafts answers in VERA's evidence-based format.
It is experimental, and its release includes neither base-model weights nor training
or evaluation datasets. The results below describe the step-400 experiment and its
historical runtime, not acceptance of the later `vera-evidence-v2` contract.

## Provenance

| Item | Value |
| --- | --- |
| Base | `Qwen/Qwen3.5-4B`, revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` |
| Adapter | LoRA rank 8, alpha 16, dropout 0, seven projection modules |
| Training | FP32, 400 optimizer updates, approximately 0.81 epoch |
| Training prompt | Historical pre-v3 answer contract |
| Data | Synthetic targets without expert review |

The later English-only v3 evaluations used mechanically aligned prompts without
retraining this adapter. The v3 candidate preserves the existing targets and is not
authorized for training. Public release of this adapter does not authorize training
on the dataset or production deployment.

## Local validation

A four-case offline comparison used the same Q6_K base model with the LoRA disabled
and enabled. ReAct and live sources were disabled, and each variant used temporary
databases and repository-bundled snapshots. The system prompt was identified by
SHA-256 `010be6a57f95bfbb34e27478cc496576b5ca72c5e3d4c35ddd6393a8b18272c7`.
The run used English output and a 4,096-token output limit.

Under the permissive status/citation criterion, the base passed 2/4 cases and the
adapter 3/4. Requiring zero validation errors reduced the result to 2/4 for both:
the adapter's missing-CVE answer still had one error. Both models classified the
PowerShell question as out of scope.

The adapter gave a concise grounded CWE-89 answer and marked the missing CVE
unavailable; the base summary included a contradictory XSS statement for CWE-89 and
combined an unavailable CVE result with a supported-fact claim. Both handled the
recipe question as out of scope.

These four cases are a smoke check, not an accuracy benchmark or deployment approval.
The citation validator used in that run did not verify every summary sentence. The
current runtime instead holds non-extractive model summaries for human review.

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

The artifact contains `adapter_config.json`, `adapter_model.safetensors` and the
tested `vera-step400-lora-f16.gguf` conversion, with SHA-256 digests in
`step400-adapter.sha256`. It contains no datasets, runtime databases, credentials
or base-model weights.

## Serving

Use the pinned base model under its own license terms. The repository includes both
the PEFT adapter and the tested F16 GGUF conversion. Applying the LoRA to a quantized
GGUF differs numerically from merging before quantization; validate the served model
and retain VERA's human-review gate.
