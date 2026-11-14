# Step-400 adapter: purpose, evidence and limits

The step-400 adapter is best understood as a response formatter with learned
evidence-handling conventions, not a demonstrated incident-analysis engine.
This assessment covers the historical pre-v3 training and its later evaluations.
The [v4 guide](kaggle-finetuning.md) records the subsequent training authorization,
run and results; neither experiment authorizes deployment of the current runtime.

## What it learned

The training objective was to make Qwen3.5-4B follow VERA's answer contract: valid
JSON, appropriate scope, explicit claim statuses, verbatim quotations and no facts
established by memory alone. It was not intended to refresh cybersecurity knowledge
in the weights.

The English-only policy arrived after training. Evaluating with v3-aligned prompts
therefore measured how the existing adapter behaved under that policy, not an
English-only training objective.

| Metric on 110 validation cases | Base | Adapter 400 |
| --- | ---: | ---: |
| Valid JSON | 91.8% | 100% |
| Valid schema | 88.2% | 100% |
| Correct scope | 82.7% | 100% |
| Mean claim-status recall | 0.670 | 1.000 |
| Citation failures | 28.9% | 0.9% |
| Memory-citation violations | 10 | 0 |
| Mean output tokens | 482 | 218 |
| Mean seconds per answer | 44.1 | 25.1 |
| Strict contract passes | 43/110 | 109/110 |

On the 220-row test pack, strict passes were 86/220 versus 219/220. The adapter's
only failure was a non-verbatim `vulnerability_triage` quote. On the 40-case held-out
probe it passed 32/40 rules against 22/40 for the base, or 31/40 against 20/40 with
grounding (`p = 0.0063` and `p = 0.0074`).

The [aligned evaluation report](finetuning-step400-evaluations.md) and
[held-out report](finetuning-step400-heldout.md) retain the full tables and caveats.

## Why those numbers were not enough

The model was mapping selected evidence into a predictable structure. With 3,939
training rows, LoRA rank 8 and seven projection modules, 400 updates were enough
to fit that structure closely. Validation loss reached 0.00044 at 0.81 epoch.
Runtime normalization already enforced some scope and structural rules.

The same regularity limited the evidence for generalization. The adapter reproduced
209/220 test summaries exactly, including 169/180 targets absent from training,
with mean token F1 0.978. Claim text matched in 210/220 cases. The base had no exact
summary matches and F1 0.110. Fifty-six of 522 test rows shared an exact target with
training, and `memory_only` and `scope_boundary` each had one target.

The v3 evaluation prompt matched the then-runtime prompt, with hash `010be6a5…`,
but the adapter had been trained on the retired prompt. Mechanical alignment
preserved all targets and did not retrain the weights.

The result was useful contract conformance and lower measured generation cost,
not verified factual correctness. No human had rated those answer packs. Alert
counts above one failed at 1/8 on the held-out family, and multi-turn had only four
held-out cases, with both variants at 3/4. Unseen tasks, source revisions and long
evidence still lacked independent evaluation. A deterministic `vera evaluate` pass
did not exercise this model at all.

## Local Q6_K A/B smoke check (2026-11-08)

The local comparison used the same Q6_K base at LoRA scales 0 and 1, temporary
databases and bundled snapshots. ReAct, live sources, graph retrieval and memory
were disabled. The prompt hash was
`010be6a57f95bfbb34e27478cc496576b5ca72c5e3d4c35ddd6393a8b18272c7`.

The permissive score was 2/4 for the base and 3/4 for the adapter. Requiring zero
validation errors gave **2/4 for both**, reproduced on 2026-11-09.

| Case | Base | Adapter | What happened |
| --- | --- | --- | --- |
| PowerShell | Fail | Fail | Both rejected the cybersecurity question as out of scope |
| CWE-89 | Pass under the smoke criterion | Pass | Base summary contradicted itself with an XSS definition; adapter was concise and grounded |
| Missing CVE-2099-99999 | Fail | Fail, one validation error | Base mixed supported and unavailable claims; adapter used only unavailable |
| Carbonara | Pass | Pass | Both rejected the unrelated request without claims |

The CWE-89 contradiction escaped the historical citation counters because they did
not verify every summary sentence. The current runtime instead requires human review
of non-extractive model summaries. `scripts/reproduce_step400.py` reproduces the
bounded local comparison using pinned public artifacts, no training data and no
live-source requests; it is not an accuracy benchmark.

## Scope probe: refusal in both directions (2026-11-09)

The earlier packs mostly checked rejection of unrelated requests. A separate probe
asked 30 cybersecurity questions, six unrelated requests and four social messages
through the same orchestrator, using bundled evidence and hash embeddings with
live sources, ReAct, graph and memory disabled.

| Family | Base marked out of scope | Adapter marked out of scope |
| --- | ---: | ---: |
| Cybersecurity, 30 cases | 6 | 19 |
| Unrelated, six cases | 6 | 6 |
| Social, four cases | 4 | 4 |

Both rejected PowerShell, SQL injection, XSS and phishing. The base also rejected
MITRE ATT&CK and server hardening; the adapter additionally rejected Nmap,
Kerberoasting, Log4Shell, MFA, ransomware, port scanning, privilege escalation,
lateral movement, zero trust and supply chain. Both answered CWE-89, CWE-79,
T1059.001, T1059, CVE-2021-44228, CVE-2023-34362, firewall and EDR.

All six unrelated refusals were appropriate. All four social decisions were wrong:
"Tell me a joke", "Hello, how are you?", "Thanks for your help!" and "Who are you?"
should have stayed in scope without claims.

The corpus contained the expected entity for 27 of the 30 cybersecurity questions.
Nmap, Kerberoasting and supply chain were genuine gaps, but needed `unavailable`,
not `out_of_scope`. Sixteen of the adapter's 19 refusals had the expected record
available in the 122-document corpus and retrievable directly. Saying "No evidence
was available" described missing citations, not missing retrieved records.

The retrieval audit found expected-record hit rates of 22/30 with hash hybrid
ranking, 23/30 with lexical ranking and 24/30 with Sentence Transformers. The latter
fixed SQLi and Log4Shell retrieval without a regression, but rerunning ten key
questions changed no refusal: the base still rejected 3/10, the adapter 5/10.
For this configuration, corpus coverage and scope decisions mattered more than
the embedding backend.

This was a bounded probe, not a universal model ranking. It nevertheless showed
that rejecting unrelated topics was not enough: on questions with a record present,
the adapter over-refused 16/30 cases against 6/30 for the base. Exact identifiers
worked better than natural-language concepts. Use `scripts/scope_probe.py` for
the probe and `scripts/retrieval_audit.py` for the ranking comparison.

## Using the adapter

The [local model guide](local-model.md#test-a-fine-tuned-adapter) covers serving,
conversion and LoRA scales. Applying an adapter to a quantized GGUF is numerically
different from merging before quantization, so evaluate the served artifact.
Inspect `metadata.model`, citations, warnings and any pending HTTP `202` review.

The appropriate role is local drafting from supplied evidence, with normalization,
explicit uncertainty and human review downstream. It is not a basis for autonomous
verdicts, unsupported alert counts or deployment on new tasks and evidence
distributions without evaluation. Its pre-v3 data and v3-aligned candidate did not
authorize further training.

## Another epoch?

There was little justification for another epoch on the same labels. Loss was
already saturated, 209/220 test summaries reproduced their targets, and new passes
could not add absent counts, richer explanations or diverse decisions.

At the time, the better use of effort was to review and train the broader v4
candidate, then write 50-60 independent golden cases. A proposed 400-to-800
falsification run would only have been informative if preregistered to improve
the held-out alert family and probe, not just validation loss. LoRA rank or learning
rate changes were secondary to the missing labels.

V4 was subsequently reviewed and trained, as documented in the
[dataset card](domain-dataset-v4.md) and [results](finetuning-v4-results.md).
Those later results do not retroactively strengthen the step-400 evidence. The
[historical dataset findings](finetuning-step400-dataset.md) retain the original
roadmap and proposed promotion thresholds; the
[golden-set guide](../finetuning/golden/README.md) defines the current 18-task procedure.
