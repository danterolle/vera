# Kaggle pilot and dataset

The standalone [notebook](../finetuning/kaggle.ipynb) targets structured cybersecurity
answer generation with **Qwen/Qwen3.5-4B**.
A five-update FP32 pilot completed on two Kaggle T4 GPUs, peaking at 9.91 and 10.15 GiB
of PyTorch-allocated VRAM. This establishes initial execution compatibility, not
quality improvement or full-epoch reliability. It does not train social replies,
intent interpretation, source assessment or ReAct decisions.

## Dataset

**The retained dataset is incompatible with the current chat prompt.**
Packaging intentionally rejects it until a compatible candidate is prepared and reviewed.
`finetuning/align.py` can rebuild a compatible copy of its prompts while preserving
targets, sources and splits. This is mechanical alignment, not new label generation
or expert review.

`vera-domain-v1.zip` and its extracted copy in `.vera/datasets/vera-domain-v1/`
are local, ignored artifacts. They contain 3,939 training, 528 validation and 522 test
conversations, plus 252 controlled event replays. Targets combine pinned public
MITRE ATT&CK and CISA KEV records with synthetic analyst scenarios, not expert SOC decisions.
Upstream revisions, hashes and license notices are preserved in the archive.

The original bytes remain unchanged. Its embedded generator instructions are historical,
and its recorded system-prompt hash is inconsistent with the conversation text.
`human_reviewed` and `training_authorized` remain false.
The earlier code bundle is retained locally as `vera-kaggle-training-pre-chat.zip`;
do not use it to train the current application.

## Training approach

Two T4 GPUs have separate memory. This recipe uses one process with **FP32 LoRA
and model sharding**, not DDP, BF16, FP16 or 4-bit QLoRA.
T4 lacks native BF16 training; Qwen3.5 has documented FP16 gradient stability issues,
and its model-specific guide discourages 4-bit QLoRA.
Full-epoch cost and memory fit for other workloads remain unverified.

The [model setup](../finetuning/vera_finetuning/model.py) pins the base revision
and uses eager attention, gradient checkpointing, LoRA rank 8 and alpha 16.
The pilot performs five updates including the longest input and largest target.
A full experiment performs one epoch with accumulation 8; neither is an optimized recipe.

## Prepare and run

To create a separate aligned candidate without model inference:

```bash
uv run --with transformers==5.17.0 --with 'jinja2>=3.1,<4' python finetuning/align.py \
  --output .vera/finetuning/aligned/vera-domain-v1.zip
uv run python finetuning/prepare.py \
  --dataset .vera/finetuning/aligned/vera-domain-v1.zip --max-length 2560
```

Use the token budget reported by alignment; this runtime's retained candidate needs
2,560 tokens. No examples are truncated or removed. The original archive is untouched.
The command validates archive hashes, actual prompts and grounded targets, then writes
`.vera/finetuning/vera-kaggle-training.zip`. It never trains, modifies the dataset,
uploads data or overwrites an existing bundle.

1. Import the notebook into Kaggle. Attach a private dataset containing the compatible
   `vera-domain-v1.zip` and `vera-kaggle-training.zip`; these exact filenames are required.
   Do not overwrite the retained original or upload credentials, databases or company telemetry.
2. Select **GPU T4 x2**, enable Internet and run preflight. Every example must fit
   the declared token budget without truncation, with a verified assistant-only loss boundary.
3. Read the warnings, set `ACKNOWLEDGE_CANDIDATE_DATA = True` and run the five-update pilot.
   Non-finite loss or gradients stop execution. Retain any OOM/kernel traceback;
   do not silently truncate examples or switch to unstable reduced precision.
4. Inspect the report, memory peaks and duration before explicitly enabling
   `RUN_FULL_TRAINING`. Save notebook outputs with Kaggle **Save Version**.

The notebook installs dependencies in a separate environment and runs training in
subprocesses. It avoids `ensurepip` and targets the environment with the image's existing pip.
Dependencies, code and base-model caches stay in a temporary runtime, outside saved outputs.
ZIPs and Kaggle-extracted directories are supported; package and per-file hashes verify
extracted contents. Subprocesses share `RUN_TIME_LIMIT_SECONDS` (1,800 by default).
Downloads are public packages and the pinned model/tokenizer;
no tracking service or automatic publishing is configured.

## Outputs and acceptance

Outputs include `report.json`, an `adapter/` directory and complete checkpoints.
Reports record package versions, hashes, losses, duration and memory peaks.
Four fixed validation losses are a numerical smoke check, not a quality benchmark.
The test split is checked for integrity/token length, never used for training or selection.

A full run checkpoints every 50 updates and at completion. To resume, preserve a complete
`checkpoint-*`, set `FULL_RESUME` and choose a new `FULL_OUTPUT`.
Data, prompt, model revision, mode and accumulation must match.

Compare base and adapted models with identical validation contexts and decoding settings.
Check JSON, citations, relevance, missing-data behavior, scope and actual VERA review outcomes.
Use the held-out test only after selection; decreasing loss is not deployment approval.

The output is a LoRA adapter, not a replacement MTP GGUF. Merge it with the same pinned
Hugging Face base, convert with a compatible llama.cpp version, then revalidate the
served artifact. Conversion and deployment are separate, manual steps.

## References

- [Qwen3.5 text-only architecture and loading](https://huggingface.co/docs/transformers/main/en/model_doc/qwen3_5)
- [Model checkpoint](https://huggingface.co/Qwen/Qwen3.5-4B)
- [Model-specific training caveats](https://unsloth.ai/docs/models/qwen3.5/fine-tune)
- [FP32 architecture guard](https://github.com/unslothai/unsloth/blob/main/unsloth/models/loader.py)
