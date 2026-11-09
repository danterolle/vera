# Step-400 adapter: purpose, evidence and limits

This page consolidates what the step-400 adapter was trained for, what later
English-only evaluations do and do not establish, how to serve it, and whether another
epoch is worth the GPU hours. It complements the run report in
[the 2026-11-01 experiment](finetuning-run-20261101.md) and the operational guide in
[local models](local-model.md#test-a-fine-tuned-adapter).

Status: experimental. The step-400 adapter was trained with the pre-v3 prompt. The v3
English-only candidate was used for later evaluation prompts, without retraining; it
declares `training_authorized: false` and contains synthetic, unreviewed targets.
Deployment is not authorized.

## What it was trained for

The adapter was not trained to add cybersecurity knowledge. Qwen3.5-4B already has the
language and domain knowledge. It was trained to make the model obey VERA's **answer
contract**:

- valid JSON matching `GeneratedAnswer`;
- correct `out_of_scope` decisions;
- expected claim statuses, including `unavailable` when evidence is missing;
- verbatim supporting quotes;
- no `supported_fact` grounded only in memory.

The English-only response rule was introduced after this adapter's training. Its
later evaluation on v3-aligned prompts measures observed behavior, not an
English-only training objective.

The measured effect on the 110-case validation pack:

| Metric | Base | Adapter 400 |
| --- | ---: | ---: |
| Valid JSON | 91.8% | **100%** |
| Valid VERA schema | 88.2% | **100%** |
| Correct scope | 82.7% | **100%** |
| Mean claim-status recall | 0.670 | **1.000** |
| Citation failures | 28.9% | **0.9%** |
| Memory citation violations | 10 | **0** |
| Mean output tokens | 482 | **218** |
| Mean generation seconds | 44.1 | **25.1** |
| Strict contract pass | 43/110 | **109/110** |

On the 220-case test pack the same comparison is 86/220 versus **219/220** strict passes.
The single adapter failure is a non-verbatim supporting quote in `vulnerability_triage`.

In one sentence: it is a **formatter and guardrail**, not an analysis engine.

## Why it worked

1. **The task is closer to mapping than to reasoning.** The model receives selected
   evidence and must emit a fixed schema. The hard part is the contract, not the domain
   knowledge.
2. **The evaluation prompt was aligned to the runtime, not the adapter's training
   prompt.** The v3 candidate uses the 3,660-character current prompt
   (`sha 010be6a5…`), but preserves all targets and was not used to retrain the
   step-400 adapter. The v1/v2 training data used the retired prompt, so the
   training/inference distribution shift remains.
3. **The dataset is low-entropy.** Most tasks have one summary or one claim text, so the
   target is nearly deterministic. LoRA rank 8 on seven projection modules is more than
   enough for a format change.
4. **The budget was sufficient.** 3,939 training rows, 0.81 epoch, 240 updates from the
   step-160 checkpoint, final validation loss 0.00044.
5. **VERA's runtime normalizer already enforces part of scope and structure**, so the
   adapter only had to learn the remaining conventions.

The same low entropy is the limit: on the 220 test pack the adapter reproduces the target
summary in **209/220** cases (**169/180** on targets not seen in training, mean token F1
**0.978**) and repeats the target claim texts in **210/220**. The base is at 0/220 exact
summaries (F1 0.110). The success is therefore real contract conformance, but largely
template fitting.

## What the evidence establishes

- On v3-aligned evaluation prompts, the adapter follows the measured English-only
  behavior in the small language probe and improves contract scores. This was not an
  English-only training run. On a 40-case probe built from the held-out test split it
  passes 32/40 versus 22/40 for the base (grounded 31/40 versus 20/40;
  `p = 0.0063` and `p = 0.0074`).
- `scope`, `unavailable` and `injection` transfer fully on that probe.
- The 220-case test pack confirms the same ordering at larger size (219/220 versus
  86/220 strict).
- The adapter is cheaper: less than half the output tokens and about 57% of the base
  latency on the same prompts.

## What the evidence does not establish

- **Factual correctness.** A strict pass means the answer obeys schema, scope, statuses
  and validators. It does not mean the analysis is right. No human has rated the answers.
- **Analysis skill.** Exact-target reproduction shows the model fits the reference
  distribution. The test split has the same template defect as training: 56 of 522 test
  rows share an exact target with training, and `memory_only`/`scope_boundary` have one
  target each.
- **Alert counting above one.** The held-out `alerts` family is **1/8** because training
  only contains zero or one configured signal.
- **Out-of-distribution robustness.** New entities, new source revisions, unseen tasks and
  long evidence are untested.
- **Multi-turn robustness.** Only four held-out cases exist, and they are at 3/4 for both
  models.
- **Production readiness.** The archive is unauthorized for training and deployment, the
  targets are synthetic and unreviewed, and citation failures must still pass the human
  review gate.
- **Training on the current prompt.** The step-400 adapter was not retrained on the
  mechanically aligned v3 candidate; its current-prompt scores do not establish what a
  properly aligned, reviewed training run would achieve.

`vera evaluate` reporting 100% with the deterministic provider is not evidence here: that
provider returns hardcoded English strings and does not exercise this model.

## How to use the adapter

Serve the base GGUF and the LoRA GGUF in one `llama-server`, then point VERA at the
alias. Full commands and the adapter-scale endpoint are in
[the local model guide](local-model.md#test-a-fine-tuned-adapter). Summary:

```bash
llama-server -m .vera/models/qwen3.5-4b-mtp/Qwen3.5-4B-Q6_K.gguf \
  --lora .vera/finetuning/adapter-step400/vera-step400-lora-f16.gguf \
  -ngl 99 -fa on --ctx-size 8192 --parallel 1 \
  --reasoning off --reasoning-budget 0 \
  --host 127.0.0.1 --port 1234 --alias vera-qwen3.5-4b-step400
```

```dotenv
VERA_LLM_PROVIDER=openai
VERA_LLM_MODEL=vera-qwen3.5-4b-step400
VERA_LLM_BASE_URL=http://127.0.0.1:1234/v1
VERA_LLM_TIMEOUT_SECONDS=600
```

`scale = 0` disables the adapter, `scale = 1` applies it fully. Applying a LoRA to a
quantized GGUF differs numerically from merging before quantization, so revalidate the
served model. Check `metadata.model`, citations and any pending `202` review on `/chat`,
and run `uv run --extra knowledge-graph python scripts/check-local-model.py`.

Appropriate uses:

- local or offline drafting of VERA-format answers from evidence already selected;
- format normalization, scope gating and `unavailable` marking;
- cost and latency reduction, with human review downstream;
- a pre-filter for the HITL gate, never a replacement for it.

Inappropriate uses:

- autonomous decisions or final verdicts;
- alert counts above one;
- new schemas, tasks or evidence distributions without a new evaluation;
- production without the review gate;
- any claim that the adapter has been shown to "analyse" incidents correctly.

## Another epoch?

**Recommendation: no, not on the current dataset.** The bottleneck is target diversity,
not optimization time.

- Validation loss is already 0.00044 at step 400. The last intervals still decrease but
  the absolute gains are tiny (0.00053 at 360 to 0.00044 at 400), and the curve is
  monotone only because the targets are nearly constant.
- Another epoch sees the same targets. It cannot invent alert counts 2 and 3, new
  summaries or new claim texts that do not exist in the data.
- More passes increase exact-target reproduction and overfitting to the template, which
  is already at 209/220. That would make the evaluation look better while making the
  model less useful.
- The v3 archive remains `training_authorized: false`; training on it requires an
  explicit decision, and the targets are still unreviewed.
- The 220-case test result does not change this: 219/220 strict with 209/220 exact target
  summaries is the signature of template fitting, not of a model that needs more steps.

If GPU hours are available, spend them in this order:

1. **Build the v4 dataset** against the current prompt with diverse summaries and claim
   texts, alert counts 0-3, short verbatim quotes, multi-turn cases and human-reviewed
   targets. Keep it unauthorized until review is complete; then train only on the
   explicitly authorized candidate. This is the only change that addresses the measured
   defect.
2. **Write a golden set by hand** (50-60 cases, 11 tasks, independent targets) with
   fact-based scoring and a human review sample. Require targets to be absent from
   training and unique within the pack; the current v3 candidate fails that criterion.
   It needs no GPU and answers the question the current packs cannot answer.
3. **Run a pre-registered falsification experiment** only if the goal is to test the
   saturation claim: resume 400 -> 800 on the same data and require an improvement on the
   held-out `alerts` family and on the 40-case test probe, not on validation loss. If
   those do not improve, stop. Expected outcome: no improvement.
4. **Tune LoRA rank or learning rate** only after v4 exists; on the current data those
   knobs cannot add missing rules.

## Local Q6_K A/B smoke check (2026-11-08)

The current VERA runtime was exercised with the same Q6_K base model at LoRA scale 0
and 1. ReAct, live sources, the knowledge graph and memory were disabled; each variant
used a temporary database and only repository-bundled corpus snapshots. The prompt hash
was `010be6a57f95bfbb34e27478cc496576b5ca72c5e3d4c35ddd6393a8b18272c7`. The
permissive result was 2/4 base versus 3/4 adapter. With a strict zero-validation-error
criterion, the result is **2/4 for both**; neither score is a statistically meaningful
quality estimate.

| Case | Base | Step-400 | Observation |
| --- | --- | --- | --- |
| PowerShell explanation | Fail | Fail | Both classified the request as out of scope. |
| CWE-89 | Pass* | Pass | Base summary first stated an incorrect XSS definition, then contradicted it; adapter gave a concise grounded definition. |
| Missing CVE-2099-99999 | Fail | Fail (1 validation error) | Base emitted both `supported_fact` and `unavailable`; adapter emitted only `unavailable`. |
| Carbonara recipe | Pass | Pass | Both correctly returned an out-of-scope answer without claims. |

`Pass*` reflects the automated smoke criterion, not full summary accuracy. The VERA
validator checks claim citations but does not validate every sentence in the summary;
the base's CWE-89 contradiction therefore escaped its validation counters. The
repeatable command is `scripts/reproduce_step400.py`; it downloads and verifies the
pinned public artifacts, starts and stops the local model server, and uses no training
data or live-source requests. With the script's stricter zero-validation-error check,
the adapter's missing-CVE case is a failure, even though its status is more conservative.
Re-running the script on 2026-11-09 reproduced **2/4 for both** models.

## Scope probe: refusal in both directions (2026-11-09)

The 4-case smoke flags a second issue: both models reject "Explain PowerShell". The
110- and 220-case packs report scope accuracy near 100% for the adapter, but those packs
mostly test rejection of unrelated requests. To check the other direction, a 13-case probe
asks 10 in-domain questions (tools, techniques, a weakness, a CVE), 2 unrelated requests
and 1 social message through the same orchestrator, with the same pinned model, bundled
corpus, hash embeddings, no live sources, ReAct, graph or memory. Reproduce with
`scripts/scope_probe.py`; the full answer text is in the JSON report.

| Family | Base `out_of_scope` | Adapter `out_of_scope` |
| --- | ---: | ---: |
| In-domain, 10 cases | 3 | 5 |
| Unrelated, 2 cases | 2 | 2 |
| Social, 1 case | 1 | 1 |

Both models rejected **PowerShell** and **SQL injection**. The base additionally rejected
**MITRE ATT&CK**; the adapter also rejected **Nmap**, **Kerberoasting** and **PowerShell
logging**. Both answered CWE-89, CVE-2021-44228, firewall and T1059.001. Both correctly
rejected the recipe and weather requests, and both marked "Tell me a joke" as
`out_of_scope`, although the contract says social conversation must return
`out_of_scope=false` with no claims.

This is not a retrieval gap. A direct `LocalCorpus.search` on the same bundled snapshots
returns CAPEC-66, OWASP A03 and CWE-89 for the SQL-injection query, and T1059.001 plus
mitigations for the PowerShell query. The refusals are model-side, and the "No evidence
was available" line in those answers describes the absence of citations, not the absence
of retrieved records, which makes the message misleading.

Interpretation, bounded by 13 cases and one configuration: the adapter learned to reject
unrelated topics but not when to accept an in-domain tool question; it is **more
conservative than the base**, not better at scope. The variable is the natural-language
concept phrasing, since exact identifiers were answered. Before any promotion, scope needs
a two-sided criterion (accept in-domain, reject unrelated, classify social correctly), and
the single `scope_boundary` target in the dataset cannot teach it.

## Test roadmap

| Priority | Test | What it would establish | Dependency |
| --- | --- | --- | --- |
| P0 | Dataset v4 + training | Whether diverse targets teach the rules | Dataset generator |
| P0 | Fact-based / paraphrase scoring | Correctness instead of target equality | Scorer or judge model |
| P0 | Human review of 30-50 answers | Factual accuracy and usefulness | Reviewer time |
| P1 | Independent scenario set | Generalization beyond v3 templates | New reviewed targets; `--require-independent-targets` |
| P1 | Two-sided scope and social control | Over-refusal of in-domain questions and social misclassification | `scripts/scope_probe.py`; new cases |
| P1 | Base + prompt ablation | Adapter effect versus prompt/normalizer effect | None |
| P1 | Multilingual probe | English-only contract on IT/ES/DE queries | None |
| P1 | Expanded multi-turn | Context and entity carry-over | New cases |
| P1 | Injection / memory poisoning | Instruction resistance and citation integrity | New cases |
| P2 | Alert counting 0-3 | Counting rule after v4 training | v4 data |
| P2 | Citation and long-context stress | Robustness near the output limit | New cases |
| P2 | Calibration and abstention | False confidence on missing evidence | New cases |
| P2 | Usage and latency capture | Real token and time costs | Runner change |

## Promotion criteria (proposal)

The adapter should not move beyond experimental use until, on a v4, independently authored
test set, it meets at least:

- 90% strict contract passes and 95% factual accuracy on human review;
- citation failure rate at or below 1%, with zero memory citation violations;
- 90% or better on alert counts 0-3 and on multi-turn cases;
- no regression on the English-only contract.

Until then it remains a draft generator behind the review gate.
