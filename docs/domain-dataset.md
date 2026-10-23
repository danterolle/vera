# Retained VERA domain dataset candidate

The experimental fine-tuning code, Kaggle notebooks, installers and obsolete bootstrap
datasets have been removed. This dataset is retained for a later evaluation of model
selection and training requirements; it is not loaded by VERA at runtime.

## Preserved artifacts

| Location | Contents |
| --- | --- |
| `vera-domain-v1.zip` | Original data-only archive, visible in the repository root |
| `.vera/datasets/vera-domain-v1/` | Identical extracted dataset, manifests and audit receipts |
| `.vera/datasets/public-snapshots-v1/` | Original public JSON snapshots, licenses and download hashes |

These are local, ignored artifacts, not files distributed through Git.
The retained ZIP and its contents are unchanged. Its embedded `DATASET.md` describes the
historical generator; commands referencing the removed training pipeline are no longer
available. Retaining those original bytes preserves the package's existing checksums.

## Actual composition

| Split | Conversations | Distinct factual texts | Multi-evidence answers |
| --- | ---: | ---: | ---: |
| Train | 3,939 | 2,302 | 2,155 |
| Validation | 528 | 272 | 256 |
| Test | 522 | 273 | 253 |

The 4,989 conversations combine real public source records with explicit synthetic analyst
scenarios. They are not production incidents, human HITL approvals or expert annotations.
Factual targets are verbatim quotations; cautious conclusions are separately labeled
`system_inference`. Traffic findings are labeled `simulated`.

Scenario families cover vulnerability triage, graph evidence, absent records, memory-only
context, unavailable live verification, untrusted notes, synthetic revision feedback,
comparisons, missing local applicability, scope and stream triage.
The 252 controlled event replays include bursts, below-threshold counts, split sources,
window boundaries, slow activity and declared maintenance. Their events and expected rules
are retained for later recomputation.

## Sources and licenses

| Source | Pinned revision | Terms |
| --- | --- | --- |
| MITRE Enterprise ATT&CK STIX | `c2494b29dd268c46a5d0ea0990553e4327cd2253` | MITRE ATT&CK license, included |
| CISA KEV | `fd12990e9c566a1ad3060e1a2073129778f438cc` | CC0-1.0, included |

The KEV snapshot is catalog `2026.10.21`. Neither source represents a current live lookup.
`sources/` preserves original field text, selected fragments, field paths, revisions and
source URLs. `licenses/` contains upstream notices, including MITRE's required attribution.
The retained raw snapshots have their own SHA-256 manifest.

## Limits and future use

The recorded split groups join CVE/product families, ATT&CK parent/subtechnique families,
identical fragments and near-duplicate excerpts. Comparison partners and distractors come
from the same split. Traffic scenario regimes are separately held out.

The included `quality-report.json` and `token-budget.json` document checks performed when
the archive was generated. The longest complete conversation is 1,994 tokens under the
pinned Qwen tokenizer, including the assistant target. These receipts do not establish
expert label quality, generalization to real telemetry, T4 memory fit or training stability.

The package remains `purpose: "domain_sft_candidate"` and `training_authorized: false`.
No model was trained. It is not directly a DistilBERT classification dataset: intent,
relevance or entailment tasks would need explicit task-specific labels and appropriate
input lengths. An uncited document must not automatically be labeled irrelevant.

There is currently no supported fine-tuning command or Kaggle workflow in this repository.
