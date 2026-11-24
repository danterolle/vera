# Kaggle training and evaluation

VERA's fine-tuning experiments teach Qwen3.5-4B to produce structured answers from
supplied cybersecurity evidence. They do not train retrieval policy, ReAct decisions
or tool use. The [notebook](../finetuning/kaggle.ipynb) completed a five-update
compatibility pilot and one full v4 epoch on two Kaggle T4 GPUs.

Deployment is still unauthorized. The current runtime contract, `vera-evidence-v2`,
checks every cited record, retains failures through retries and repairs, and sends
non-extractive model summaries and fallbacks for human review. Earlier measurements
remain useful history, but do not qualify this changed runtime.

## The reviewed dataset

The archived v4 package contains 5,406 training, 686 validation and 720 test
conversations, plus 160 controlled event replays. It combines pinned public ATT&CK
and CISA KEV records, 122 bundled official documents and synthetic analyst scenarios.
These are source-grounded targets, not expert SOC decisions. Source revisions,
checksums and license notices travel with the archive.

Compared with v1/v3, it adds in-domain and unavailable concepts, social and
clarification turns, multi-turn follow-ups, language variants and alert counts 0-3.
Both prompts were rebuilt from the runtime used for that experiment. The
[dataset card](domain-dataset-v4.md) explains the task mix and source boundaries.

`danterolle` accepted the 80-case review pack on 2026-11-11. The authorized derivative
preserved the reviewed shards byte-for-byte, set `human_reviewed` and
`training_authorized` to true, and added `AUTHORIZATION.md`. These hashes identify
the archived authorization:

| Artifact | SHA-256 |
| --- | --- |
| Reviewed manifest | `485bd329a5c3409929b17f7618b3cd95e0a35bcbccc8a29a7dd863437823d98d` |
| Authorized manifest | `04d18fbb7db8b35571bff755f43ad3eadadbc3c30d01d3f54426bfbcf27feb10` |
| Authorized package | `6a3b5aa90252cecabc0560f2376929c8b4d0f7b38f85f580e98af011a1c0cd24` |
| Authorized dataset archive | `f0e288f4bf78be8a351f3a7f403a7fe0c870c6137af44c2b1b7f0bf611997142` |
| Authorized Kaggle bundle | `f13248e11a6a5d0f99ac905fd8ee50d89de98f2f0884a41c2cb1b1928fa8ce48` |

Training authorization was separate from permission to launch the GPU run, and neither
authorized deployment. Local datasets and weights remain ignored by Git.

## New candidates are not the archived package

The generator now expands summaries with cited source content and no longer teaches
citing a distractor merely because the main record lacks a mitigation companion.
That changes targets, not the existing authorized archive or trained weights.
Any replacement needs its own review, authorization and token-budget receipt.
The old 2,560-token receipt does not qualify expanded targets.

To build a fresh candidate without overwriting the archived v4 data:

```bash
uv run python finetuning/vera_domain/cli.py \
  --output .vera/datasets/vera-domain-v4-candidate
```

Generation loads no weights, calls no external language model and performs no training.
It verifies source hashes and refuses an existing output directory or archive.
Review the candidate using the [dataset procedure](domain-dataset-v4.md#human-review)
before considering a training authorization.

## Token budget

The archived v4 preflight passed at `max_length=2560` without truncation and verified
the assistant-only loss boundary. Its maximum sequence was 2,462 tokens; its largest
target was 543. A 2,048-token budget would lose 80 `stream_triage` rows, and 2,304
would still truncate 48. Keeping two- and three-alert examples was part of the task,
so dropping them to fit a smaller budget was not acceptable.

`token-budget.json` binds those findings to the manifest SHA-256. Packaging rejects
a mismatched receipt. For a replacement candidate, measure the complete sequences
again rather than assuming that the archived budget still fits.

User-facing prose follows `Settings.response_language`, defaulting to English,
while evidence quotations retain their original wording and language.

## Training approach

The recipe uses one process, FP32 LoRA and model sharding across two T4 GPUs.
Their memories are separate; this is not DDP, BF16, FP16 or four-bit QLoRA.
T4 has no native BF16 training, Qwen3.5 has documented FP16 gradient-stability issues,
and its model-specific guide discourages four-bit QLoRA.

The [model setup](../finetuning/vera_finetuning/model.py) pins the base revision
and uses eager attention, gradient checkpointing, LoRA rank 8 and alpha 16.
The pilot runs five updates, including the longest input and largest target.
A full run uses accumulation 8 and `--epochs` passes, defaulting to one, with a
deterministic reshuffle each epoch. A complete checkpoint preserves optimizer state,
epoch and data cursor for resuming.

For bounded runs, `--max-steps` is an absolute update limit. `--validation-every`
and `--validation-examples` control fixed-sample loss monitoring. The recipe is
conservative rather than optimized, and fit or cost on other workloads is unverified.

## Prepare and run

`finetuning/prepare.py` checks archive hashes, actual runtime prompts and grounded
targets, then writes a data-free code bundle. It refuses examples above the declared
token budget and never trains, edits the dataset, uploads it or overwrites a bundle.
For reference, the archived v4 packaging used:

```bash
uv run python finetuning/prepare.py \
  --dataset .vera/datasets/vera-domain-v4.zip --max-length 2560 \
  --output .vera/finetuning/vera-kaggle-training-v4.zip
```

This records the archived recipe, not approval of a newly generated candidate.
Current checks may reject historical data that no longer meets the runtime contract.
Use the reviewed bytes, a matching receipt and a fresh output path for any new run.

On Kaggle, import the notebook and attach a private dataset containing files named
exactly `vera-domain-v4.zip` and `vera-kaggle-training.zip`. Use the authorized archive
and matching bundle, renaming the uploaded files as required. Never upload credentials,
runtime databases or company telemetry.

Select **GPU T4 x2**, enable Internet and run preflight. Every example must fit
without truncation, with the assistant-only boundary verified. After reading the
warnings, explicitly set `ACKNOWLEDGE_CANDIDATE_DATA = True` to run the pilot.
Non-finite loss or gradients stop execution; retain any OOM or kernel traceback
instead of silently truncating data or switching to unstable precision.

Inspect the pilot's duration and memory before enabling `RUN_FULL_TRAINING`.
For a bounded preview, set `MAX_STEPS`, retain `VALIDATION_EVERY`, and enable
`RUN_BEHAVIORAL_EVAL` for a paired validation sample. Save outputs with Kaggle's
**Save Version** action.

The notebook uses a separate dependency environment and subprocesses, targeting the
image's existing pip rather than `ensurepip`. Dependencies, code and model caches
stay in temporary storage. ZIPs and extracted datasets are both supported and checked
against package/file hashes. Subprocesses share `RUN_TIME_LIMIT_SECONDS`, whose
default is 1,800. There is no tracking service or automatic publishing.

## Outputs and acceptance

Runs write `report.json`, append-only `metrics.jsonl`, an `adapter/` directory and
complete checkpoints every 50 updates and at completion. Reports retain package
versions, hashes, losses, validation history, timing and memory peaks; metrics include
updates completed before a timeout. Resume with a complete `checkpoint-*`,
`FULL_RESUME` and a new `FULL_OUTPUT`, keeping data, prompt, model revision, mode and
accumulation unchanged.

Loss is an optimization check, not an acceptance criterion. Compare base and adapter
on identical contexts and decoding settings, inspect raw and repaired behavior
separately, and reserve the test split until selection is complete. Once consumed,
it must not be reused to tune or select a model. The
[evaluation guide](finetuning-evaluation.md) covers scoring, independent targets and
human review.

The training output is a LoRA adapter, not a replacement MTP GGUF. Merging with the
same pinned base, converting with a compatible llama.cpp version and validating the
served artifact are separate manual steps.

## v4 runtime guard and merged artifact (2026-11-13)

The [v4 results](finetuning-v4-results.md) record the epoch, paired behavioral
measurements, historical relevance guard and merged Q6_K artifact. They also explain
why the old 40-answer review pack cannot qualify `vera-evidence-v2`.

For earlier experiments, see the [80-update preview](finetuning-preview-20261028.md),
[step-400 report](finetuning-run-20261101.md) and
[adapter assessment](finetuning-adapter-assessment.md).

## References

The recipe follows the [Qwen3.5 architecture documentation](https://huggingface.co/docs/transformers/main/en/model_doc/qwen3_5)
and the pinned [model checkpoint](https://huggingface.co/Qwen/Qwen3.5-4B).
The [model-specific training caveats](https://unsloth.ai/docs/models/qwen3.5/fine-tune)
and [FP32 architecture guard](https://github.com/unslothai/unsloth/blob/main/unsloth/models/loader.py)
explain the conservative precision choice.
