# V4 training and behavioral results

The authorized v4 dataset completed one epoch on 2026-11-12. These results describe
the frozen adapter and the runtime used on 2026-11-12/13, not acceptance of the later
`vera-evidence-v2` contract. Deployment remains unauthorized.
The [training guide](kaggle-finetuning.md) and [dataset card](domain-dataset-v4.md)
record the recipe, review and package hashes.

## The completed epoch

Training covered 5,406 examples in 676 optimizer updates with accumulation 8 and a
2,560-token budget. It took two Kaggle sessions. The first saved
`checkpoint-000350` and reached step 387 before its wall-clock budget expired.
The second resumed from step 350 for 326 updates, discarding the intervening 37.

The resumed segment took 35,093 seconds, or 9.75 hours. The first subprocess ran
11.4 hours, so the two sessions cost about 21 hours of T4 x2 time in total.

| Metric | Recorded value |
| --- | --- |
| Optimizer updates | 676 / 676 |
| Training examples | 5,406 |
| Peak allocated VRAM | 9.89 / 10.15 GiB |
| Validation loss | 0.0177 at 350; 0.0084 at 600; 0.0146 at 676 |
| Final training loss | 0.0023 |
| Truncation and warnings | None |

The final 41 MB adapter stayed local. Near-zero training loss and saturated
validation loss showed template fit, not general capability. The test split was
not used for checkpoint selection.

## Paired validation and test samples

Each pack selected three examples from each of 18 tasks, with a 768-token output
limit. Every example was answered by both base and adapter.

| Selection | Validation, 2026-11-12 | Test, 2026-11-13 |
| --- | --- | --- |
| Examples | 54 | 54 |
| Seed | 20261102 | 20261113 |
| Selection SHA-256 | `54eee0b8d9b7984739af79abf7663c7dc8921d206dcbd787902ba0611259fc7f` | `da626b6a67829cb36c649cfa376d07fea3343b023af5a27203831b8480f0612c` |
| Training-target overlaps | 12 | 12 |
| Duplicate rows within pack | 5 | 5 |
| Generation time | 3,147 s, 52.5 min | 2,904 s, 48.4 min |
| Kernel time including install/load | 1 h 34 min | 53 min |

Validation excluded the 24 parent IDs used for loss monitoring. The test pack was
run once after freezing the adapter. It is held out by row, not independently
authored, and is now consumed.

| Metric | Validation base | Validation adapter | Test base | Test adapter |
| --- | ---: | ---: | ---: | ---: |
| Valid JSON | 90.7% | 98.1% | 92.6% | 100% |
| Valid schema | 88.9% | 98.1% | 83.3% (45/54) | 100% |
| Correct scope | 87.0% | 98.1% | 81.5% | 100% |
| Mean status recall | 0.719 | 0.981 | 0.667 | 0.963 |
| Unavailable present, 12 expected | 8/12 | 11/12 | 6/12 | 10/12 |
| Citation failures, schema-valid rows | 8.3% | 0% | 13.3% | 0% |
| Exact-quote claims | 98.0% | 100% | 88.1% | 100% |
| Memory-citation violations | 0 | 0 | 0 | 0 |
| Mean output tokens | 399 | 190 | 386 | 183 |
| Mean seconds per answer | 36.6 | 21.7 | 34.7 | 19.1 |

On the 42 validation targets absent from training, the adapter had valid schema
and scope in 42/42 cases with status recall 0.976; the base scored 85.7%, 85.7%
and 0.653. On the 42 unseen test targets, the adapter again reached 42/42 for
schema and scope, with recall 0.952. These remain template-adjacent samples.

### What still failed

The validation adapter wrote one social reply as prose rather than JSON, despite
that target appearing in training. It also used `system_inference` instead of
`unavailable` for a statement that no local DNS-tunnelling record was established.
The base failed schema on six cases, including all three stream cases, and had
citation errors in `current_status` and `graph_evidence`.

The test pack exposed a more serious weakness: `unavailable_concept` passed only
1/3 cases. For "supply chain attack" and "firmware implant", the adapter cited
Overwrite Process Arguments and Stripped Payloads as supported facts. One answer
even acknowledged the entity mismatch while citing it.

The base also failed those cases, but one base answer was schema-invalid. The
adapter made the same relevance error fit the schema. Clean formatting and exact
quotations therefore did not establish that the answer concerned the question.

## The historical runtime guard

The first guard checked whether any supplied knowledge record named the subject.
If none did, it relabeled knowledge-backed factual claims as unavailable. Memory,
stream, simulated and fallback records did not qualify; identifiers matched exactly
and concept tokens had to occur together in a name or alias.

On all 1,406 validation/test gold targets, containing 1,737 supported claims, the
guard changed nothing. Rescoring the existing generated answers, without rerunning
the test split, gave:

| Metric | Adapter | Adapter plus historical guard |
| --- | ---: | ---: |
| Valid schema | 54/54 | 54/54 |
| Correct scope | 100% | 100% |
| Mean status recall | 0.963 | 1.000 |
| Unavailable present, 12 expected | 10/12 | 12/12 |
| Relevance failures | 2/54 | 0/54 |
| Citation failures | 0% | 0% |

The guard did not intervene on validation: schema remained 53/54, recall 0.981,
unavailable 11/12 and `unavailable_concept` 2/3. It fixed the measured test failure,
not every missing behavior.

The current contract is stricter. It checks each citation rather than letting one
on-topic record license other records, retains failures through automatic retries
and repairs, and requires review of non-extractive model summaries and fallbacks.
The earlier practice of clearing errors after relabeling is no longer the policy.

## Merged artifact and recorded checks

The adapter was merged into base revision `851bf6e8` using PEFT on
`Qwen3_5ForCausalLM` in BF16, converted to GGUF BF16 and quantized to Q6_K.
The served 3.2 GB Q6_K file contains the merged weights and uses no `--lora`.

| Artifact | SHA-256 |
| --- | --- |
| `adapter/adapter_model.safetensors` | `927d384c922e8523000ce8b9445de03e6650dde17098f548e07f4e1065151b4b` |
| Merged BF16 GGUF | `053007ea347f71bd132c55f2d086a260c25a59829da78018506dc68c4dd49f03` |
| Merged Q6_K GGUF | `872292b16661ab123e51f588d857592c0eab0d1d74aae0615d1310e954ec21a6` |
| `guard-regression-v4.json` | `dd46677ec6eb6165f533dd6ef493f21233da9e7a0d21030dec076f9905c78586` |
| `local-model-checks-v4-merged-final.json` | `abe8e75e7a2005abf70d901f8a000a80734137ab4432c0406e78816d3bc181a6` |

The final historical `scripts/check-local-model.py` run passed four cases after
the review-repair fixes. The earlier output remains in
`local-model-checks-v4-merged-guarded.json`. Four checks were not a production gate,
and neither output qualifies today's changed runtime.

## The pending human review

The merged runtime produced a 40-answer pack on 2026-11-13 at
`.vera/reviews/v1/pack-20261113`, with SHA-256
`38a0f1cde68c3001bb61157f3dfd4b5d3f40d5b2281cc2e16235c21bc0b0f6a6`.
Three cases paused for review, `rv-010`, `rv-027` and `rv-029`. Case `rv-006`
hit the generation limit and used a deterministic fallback. Verdicts and sign-off
were still pending.

That pack predates `vera-evidence-v2`, so accepting it cannot qualify the current
runtime. A fallback is not a successful model answer either. The next acceptance
work needs fresh independent outputs and a real human review, followed by explicit
authorization. The consumed test split must not be used for further tuning.
