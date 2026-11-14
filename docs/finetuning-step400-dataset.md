# What the step-400 data taught the model

The [step-400 experiment](finetuning-run-20261101.md) achieved nearly perfect scores
on its reference distribution. Looking at the data explains both that success and
the behaviors that did not transfer. These findings describe the historical v1-v3
work; the [v4 guide](kaggle-finetuning.md) records what happened afterward.

## Prompt drift and short targets

The training dataset contained a 1,722-character system prompt. The runtime used
3,604 characters during the original experiment and later 3,660 under the English-only
policy. These were materially different contracts:

| Training prompt | Runtime used in the original run |
| --- | --- |
| At most three summary sentences and three short claims | Detailed explanations and up to six supported claims |
| No language rule | Mirror the latest question's language |
| No conversation rules | Resolve follow-ups and preserve continuity |
| No `conversation` context | Supplied `current_subject` and `conversational_intent` |

The targets fit the older prompt. Median summary length was 14 words, with a p90 of
16, and 97.2% had no more than three sentences. Across `scope_boundary`, `memory_only`,
`current_status` and `risk_comparison`, 1,445 of 3,939 training rows shared one summary
per task. All 1,332 `vulnerability_triage` examples had exactly three claims.

This made terse, repeated wording an expected outcome of training. In the historical
local project-suite comparison, the adapter produced one factual claim against 17
for the base, source coverage of 0.30 against 0.71 and grounding of 0.33 against 0.77.
Those figures describe that run, not the current runtime.

Mechanical v2 and v3 alignment changed prompts but **zero assistant targets**.
The v3 prompt hash was `010be6a5…`. That removed evaluation-prompt drift without
retraining the adapter or supplying richer labels.

## Why alert counting failed

Training `stream_triage` contained 72 zero-alert rows and 36 one-alert rows. The
perturbed probe instead asked for zero, two and three alerts. The adapter passed
the two zero-alert cases and failed all six multi-alert cases.

In two failures, valid JSON said only that configured thresholds had fired, without
giving a count. In four, a quote copied the whole evidence payload and exhausted
the 768-token output budget, leaving truncated JSON. The later English-only probe
also showed five truncated adapter answers among its eight alert cases.

These are distinct problems: the targets did not teach counting above one, and their
long quotations made the output format fragile. More updates on the same labels
would not add missing counts or shorten the expected quote.

## The historical language probe

The original policy asked the model to answer in the latest question's language.
A local Q6_K comparison used four Italian questions, four English twins with identical
evidence and route, and Italian versions of the unavailable/scope cases:

| Cases | Base | Adapter |
| --- | ---: | ---: |
| Four Italian questions, Italian answer expected | 0/4 | 0/4 |
| Four English twins, English answer expected | 4/4 | 4/4 |
| Missing-evidence rule asked in Italian | 0/1 | 1/1 |
| Scope rule asked in Italian, raw output | 0/1 | 0/1 |

The FP32 base's earlier 4/4 Italian result did not carry over to this local
provider/precision configuration. In one Kaggle CVE case the adapter answered in
English and refused despite relevant evidence. A language score alone therefore
missed whether the question was understood.

Both raw scope failures set `out_of_scope=true` while retaining a claim; the runtime
normalizer removed that claim. Those were measurement differences, not failures of
the normalized application behavior.

The English-only policy introduced on 2026-11-02 made the Italian-answer expectation
obsolete, but did not make refusal of relevant Italian questions correct. Subsequent
checks needed to consider configured output language, understanding and evidence use
together. The first multi-turn probe also remained a warning: base 4/4, adapter 2/4,
including an incorrect fallback about missing local-applicability evidence.

## What the splits did and did not protect

Training IDs were disjoint from validation and test. That did not prevent answer
templates from repeating: 57 validation targets occurred verbatim in training and
55 rows duplicated another validation target. Later canonicalized audits found
56 of 522 test rows sharing a target with training.

The 110- and 220-row validation packs excluded the first 33 behavioral cases and
24 fixed loss rows, with source groups and entities disjoint from training. They
still contained 20/40 exact training-target overlaps and 18/38 duplicate rows.
Increasing their size broadened the sample without making the targets independently
authored.

## The v4 response

At the time of this assessment, v4 was a built and audited candidate, not an
authorized training run. It added in-domain definitions, defenses and explicit
unavailable concepts; social and clarification turns; multi-turn context; IT/ES/DE/FR
questions answered in English; and replays with zero through three alerts.

The archived package eventually contained 5,406 train, 686 validation and 720 test
rows, with 2,319 distinct training factual texts and 2,535 multi-evidence answers.
Its training alert counts were 5,316 / 40 / 30 / 20 for zero through three signals.
The recorded 2,560-token budget preserved multi-alert cases. Authorization and the
subsequent run are documented in the [dataset card](domain-dataset-v4.md) and
[v4 results](finetuning-v4-results.md).

Its broader coverage did not make the targets expert decisions. Defensive guidance
and multi-turn families used all eligible mitigation-linked entities, but still
followed authored templates, as did social and clarification replies.

## Evaluation priorities proposed at the time

| Priority | Work | Question it addresses |
| --- | --- | --- |
| P0 | Reviewed v4 data and training | Do more diverse labels teach the missing rules? |
| P0 | Fact-based or paraphrase scoring | Is the answer right, not just identical? |
| P0 | Human review of 30-50 answers | Are the findings correct and useful? |
| P1 | Independent scenarios | Does behavior transfer beyond the templates? |
| P1 | Two-sided scope and social controls | Does the model accept as well as reject correctly? |
| P1 | Base/prompt ablation | What does the adapter add beyond prompts and normalization? |
| P1 | Multilingual and expanded multi-turn probes | Are language understanding and context preserved? |
| P1 | Injection and memory poisoning | Are untrusted instructions and citations handled safely? |
| P2 | Alert counts 0-3 | Does the missing counting behavior transfer? |
| P2 | Long context and citation stress | What happens near the output limit? |
| P2 | Calibration and abstention | Does missing evidence produce false confidence? |
| P2 | Usage and latency capture | What does the served system actually cost? |

The historical promotion proposal called for at least 90% strict-contract passes,
95% factual accuracy on human review, citation failures no higher than 1%, zero
memory-citation violations, at least 90% on counting and multi-turn, and no
English-output regression. These were proposed targets, not achieved results or
an automatic authorization policy.
