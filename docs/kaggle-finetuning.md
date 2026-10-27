# Kaggle fine-tuning pilot

This is an experimental, standalone workflow for **Qwen/Qwen3.5-4B**.
It does not change VERA's runtime, start training locally, publish data, or authorize deployment.
The notebook and training utilities have not been executed on Kaggle T4 hardware.
Memory fit, kernel support, throughput and quality improvement remain unverified.

## Current dataset compatibility

The chat integration changes the system prompt, conversation context and claim limit.
The retained `vera-domain-v1.zip` predates that contract. The packager now intentionally
rejects it: generate and review a new dataset version before preparing current-runtime inputs.
The earlier local code bundle is retained as `vera-kaggle-training-pre-chat.zip` for
traceability, not as a valid upload for the current chat application.
This pilot targets structured cybersecurity answer generation. Conversational replies,
intent interpretation, source assessment and ReAct decisions require separate examples
and evaluation; they are not covered by this dataset contract.

## Why this recipe is conservative

Two T4 GPUs have separate memory. DDP creates one model replica per GPU; it does not
give each replica 32 GB. This recipe instead uses one Python process and distributes
the text model's layers across both devices, without CPU or disk offload.
It uses ordinary autograd, not an inference-only `no_grad` execution path.

T4 does not provide native BF16 training. Qwen3.5's Gated DeltaNet layers also have
documented FP16 gradient stability problems: Unsloth explicitly lists `qwen3_5`
among architectures requiring its FP32 fallback. Its model-specific guide additionally
discourages 4-bit QLoRA for this family.

Consequently this pilot uses the text-only `Qwen3_5ForCausalLM`, **FP32 LoRA**, eager
attention, gradient checkpointing, batch size one and GPU model sharding.
It is slower than a validated optimized implementation and may still run out of memory.
An OOM or unsupported kernel is a failed compatibility experiment, not permission to
silently truncate the dataset or switch to FP16.

## Prepare the two inputs locally

The existing dataset ZIP is local and ignored by Git. A clone alone does not include it.
From the repository root, with the regular VERA environment installed:

```bash
uv run python finetuning/prepare.py
```

The command rechecks the archive, all conversation prompts and grounded targets against
the **currently checked-out runtime**, then writes:

```text
.vera/finetuning/vera-kaggle-training.zip
```

The code bundle contains no dataset, credentials, database or model weights. Existing
output files are not overwritten; choose another `--output` path when rebuilding.
The notebook expects the uploaded code bundle to be named `vera-kaggle-training.zip`.

The retained dataset's historical `system_prompt_sha256` does not match the actual
conversation prompt. The packager reports this inconsistency rather than changing the
original archive. It independently checks every actual system/user prompt against VERA
and binds the code bundle to the archive's SHA-256. A successful preflight is not expert
label approval. `human_reviewed` and `training_authorized` are not changed.

If `chat` or another branch changes the runtime prompt or input format, do not train
this dataset as though it matched that new contract. Rebuild and review the data first.

## Run on Kaggle

1. Create a private Kaggle dataset containing `vera-domain-v1.zip` and
   `vera-kaggle-training.zip`. Do not upload `.env`, databases, company telemetry or models.
2. Import [`finetuning/kaggle.ipynb`](../finetuning/kaggle.ipynb) as a notebook.
   Select **GPU T4 x2**, enable Internet and attach the private dataset.
3. Execute the input, environment and preflight cells. These check real tokenization
   without loading model weights. Every example must fit 2,048 tokens without
   truncation, and assistant-only loss boundaries must match the pinned chat template.
4. Read the warnings, then set `ACKNOWLEDGE_CANDIDATE_DATA = True` in the pilot cell.
   Run that cell. It loads the model on both GPUs and performs five optimizer updates,
   including the longest input and largest target. Non-finite loss/gradients stop execution.
5. Inspect `report.json`, GPU peaks and elapsed time. Only after a successful pilot,
   explicitly set `RUN_FULL_TRAINING = True` to run one training epoch.
   Keep Kaggle outputs using **Save Version**.

Training dependencies are installed in a separate environment using the notebook's
existing Torch installation when compatible. Heavy imports and training run in subprocesses;
the notebook kernel does not need to import a newly installed Transformers version.
Internet downloads only public packages and the pinned model/tokenizer. No tracking
service or automatic upload is configured.

## Settings and artifacts

| Setting | Pilot | Full experiment |
| --- | --- | --- |
| Base revision | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` | Same |
| Precision | FP32, no quantization | Same |
| Parallelism | Single-process model sharding on GPU 0 and 1 | Same |
| LoRA rank / alpha | 8 / 16 | Same |
| Learning rate | `2e-5` | Same; an initial experiment, not an optimized choice |
| Maximum sequence | 2,048, no truncation | Same |
| Gradient accumulation | 1 | 8 |
| Training duration | Five updates | One epoch |
| Numerical validation | Four fixed validation examples | Same |
| Checkpoints | End of pilot | Every 50 updates and at completion |

Outputs include adapters, tokenizer, optimizer/RNG checkpoints and a report with
actual package versions, memory peaks, durations, losses and data/contract hashes.
The test split is checked for integrity/token length, never used for training or selection.
The five-update pilot does not establish improvement.

To resume an interrupted full run, preserve a complete `checkpoint-*` directory,
set `FULL_RESUME` to that directory, and choose a new `FULL_OUTPUT`.
The checkpoint must match the model revision, data, prompt, mode and accumulation.
A previous pilot is not a full-run resume checkpoint.

If the run fails, retain the traceback and GPU information. Do not start a full epoch.
If the conservative configuration cannot fit or is impractically slow, choose a
different model/hardware or validate a specialized implementation as a separate experiment.

## Evaluation and deployment

The dataset is source-grounded synthetic data, not expert SOC decisions. Fine-tuning
should target JSON compliance, relevant quotations, uncertainty and scope handling.
It does not replace live vulnerability intelligence, retrieval, detectors or human review.

Compare base and adapted models with identical validation contexts and decoding settings.
Measure JSON validity, factual quotation correctness, unrelated-evidence use, missing-data
handling and scope behavior. Evaluate real VERA routes and review outcomes as well.
Use the held-out test only after model/settings selection; do not promote an adapter
merely because its training or four-example validation loss decreases.

The output is a **LoRA adapter**, not a deployable replacement for the existing MTP GGUF.
Merge with the same pinned Hugging Face base, convert/quantize with a compatible llama.cpp
release, and revalidate the final served artifact. Conversion and quality approval are
separate steps, not performed automatically by this notebook.

## Sources

- [Qwen3.5 architecture and text-only loading](https://huggingface.co/docs/transformers/main/en/model_doc/qwen3_5)
- [Official model checkpoint](https://huggingface.co/Qwen/Qwen3.5-4B)
- [Unsloth Qwen3.5 training caveats](https://unsloth.ai/docs/models/qwen3.5/fine-tune)
- [Unsloth FP32 architecture guard](https://github.com/unslothai/unsloth/blob/main/unsloth/models/loader.py)
- [DDP replicates the model](https://unsloth.ai/docs/basics/multi-gpu-training-with-unsloth/ddp)
