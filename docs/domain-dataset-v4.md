# VERA v4 public-evidence domain dataset

The v4 dataset teaches VERA how to answer defensive cybersecurity questions from
evidence. It combines pinned public records, official snapshots bundled with the
repository and explicitly synthetic analyst scenarios. Generation is data-only:
it loads no model weights, calls no external language model and performs no training.

This card describes the archived package reviewed by `danterolle` on **2026-11-11**,
with all 80 sampled cases accepted. Its authorized derivative sets `human_reviewed`
and `training_authorized` to true, but does not authorize deployment. The hashes below
identify the reviewed bytes. Later generator changes do not inherit that approval.

## Why v4 exists

The earlier candidate used an older prompt and covered too few behaviors. Evaluation
exposed the consequences: the step-400 adapter rejected unfamiliar cybersecurity
concepts, treated social turns as security questions and had only seen replays with
zero or one alert. The archived v4 package was rebuilt with the runtime prompts used
for that experiment and broadened each of those areas.

| Gap in v1/v3 data | v4 response |
| --- | --- |
| Prompt drift | `messages[1]` is produced by the current `generation_prompt`; `messages[0]` is the current `SYSTEM_PROMPT` |
| One-sided scope | explicit in-domain concept, defensive, unavailable-but-in-domain, social, clarification and out-of-scope families |
| Missing social handling | dedicated `social_conversation` and `clarification` targets with no claims and `out_of_scope=false` |
| Alerts only 0/1 | controlled replays with exactly 0, 1, 2 and 3 detector signals and an alert-correlation family |
| No multi-turn | follow-up conversations with resolved question, subject and search query |
| No language variants | Italian, Spanish, German and French questions answered in the configured English response language |
| Entity/title drift | targets quote evidence content verbatim and identify the entity each record concerns |

## Sources and permitted reuse

| Source | Immutable revision | Terms |
| --- | --- | --- |
| MITRE Enterprise ATT&CK STIX | `c2494b29dd268c46a5d0ea0990553e4327cd2253` | MITRE ATT&CK license, included |
| CISA KEV | `fd12990e9c566a1ad3060e1a2073129778f438cc` | CC0-1.0, included |
| Repository-bundled corpus | file hashes recorded per fragment | see upstream URLs on each record |

The KEV snapshot is catalog `2026.10.21`; neither it nor the ATT&CK snapshot is a
current API result. The package uses official JSON records and keeps their notices
under `licenses/`. Each fragment records its source URL, original field, verbatim
excerpt, field path, snapshot revision and download hash.

## Scenario families

| Family | Required behavior |
| --- | --- |
| `vulnerability_triage` | separate documented vulnerability/action from local exposure |
| `graph_evidence` | explain technique documentation without claiming local execution |
| `concept_definition` | answer in-domain definitions from the current subject, not a passing mention |
| `defensive_guidance` | cite a supplied mitigation without claiming it is deployed |
| `unavailable_concept` | say an in-domain concept is missing from the records; do not substitute a decoy |
| `language_variant` | answer in `response_language=English`, keeping quotations verbatim |
| `multiturn_followup` | resolve "it" from conversation context and keep the right subject |
| `social_conversation` | greet/thank/introduce with no claims and `out_of_scope=false` |
| `clarification` | ask for the missing subject instead of inventing one |
| `scope_boundary` | refuse unrelated requests with `out_of_scope=true` and no claims |
| `stream_triage` | report simulated detections; 0–3 signals, including correlated replays |

Knowledge families reuse the v1/v3 contract families (`missing_record`, `memory_only`,
`current_status`, `untrusted_note`, `review_revision`, `risk_comparison`,
`local_applicability`) and add the in-domain variants above.

## Size

| Split | Examples | Alert counts 0/1/2/3 | Multi-turn | Social | Clarification | Out of scope |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| train | 5,406 | 5,316 / 40 / 30 / 20 | 320 | 16 | 4 | 240 |
| validation | 686 | 662 / 6 / 12 / 6 | 40 | 8 | 4 | 28 |
| test | 720 | 696 / 12 / 6 / 6 | 40 | 8 | 4 | 30 |

The archived training split has 2,319 distinct factual texts and 2,535 answers citing
at least two records. Its 360 `defensive_guidance` and 320 `multiturn_followup` rows
use every eligible entity with a mitigation companion. The recorded maximum sequence
is 2,462 tokens, with a largest target of 543; `max_length=2560` was the smallest
tested budget that avoided truncation. Expanded targets need a fresh receipt.

## Dataset layout

```
DATASET.md                 this card
manifest.json              seed, prompt hash, upstream revisions, split counts
package.json               every packaged file with its SHA-256
quality-report.json        audit result; never an authorization
token-budget.json          optional tokenizer receipt
sources/part-*.jsonl       normalized source fragments and their split groups
train|validation|test/     conversation shards (system, user, assistant)
replays/<split>/           controlled event replays used by stream_triage
licenses/                  upstream notices
```

Splits are grouped by CVE/product, technique family, identical content and near-duplicate
source text. A source, split group or verbatim factual target must not appear in two splits.

## Limits

These targets are deterministic scenarios grounded in sources, not expert SOC
decisions or human annotations. Traffic is simulated, conversational variants are
authored templates and the sources are frozen snapshots rather than live intelligence.
An audit can establish internal consistency, not model improvement. Training or
deployment still requires human review, explicit consent and a Kaggle compatibility run.

## Human review

An audit does not authorize training. Before `training_authorized` can become true,
a person must review the targets. The review-pack builder samples every task,
including alert counts 0-3, social turns, clarification and defensive or multi-turn
questions, and produces a checklist for that review.

### AI-assisted pre-review (not a sign-off)

An AI-assisted pass read every review case and scanned the candidate for wording
that did not fit its task. It found vulnerability terminology in 265 `graph_evidence`
technique summaries, "affected versions" in 89 ATT&CK `local_applicability` questions,
and "documented issues" in 88 technique `risk_comparison` questions. The generator
was corrected, the audit was extended and the candidate was rebuilt. This advisory
pass did not set `human_reviewed` or authorize training.

### Human sign-off (2026-11-11)

The 80-case pack was reviewed with a guided pass over the highest-risk cases:
`rv-0016`, `rv-0030`, the four `stream_triage` alert profiles, the two
`untrusted_note` cases, the two `vulnerability_triage` cases with distractors,
and six dataset-wide gap examples (technique `risk_comparison`,
`graph_evidence` without a mitigation companion, vulnerability
`defensive_guidance`, `multiturn_followup` and `concept_definition`, and
technique `missing_record`).

| Field | Value |
| --- | --- |
| Reviewer | `danterolle` |
| Review date | `2026-11-11` |
| Verdicts | `accept`: 80 / 80 |
| Reviewed dataset SHA-256 | `485bd329a5c3409929b17f7618b3cd95e0a35bcbccc8a29a7dd863437823d98d` |
| Cases SHA-256 | `c5ae626f017f8e7d7ab68463ccd40f97f3accfe2caf8d7541e776518e987443e` |
| Sign-off SHA-256 | `5a60cfe0895715eef8b756b08aefeaad8eff61fcac59dfd00eb82af9ea76eeb7` |
| Summary SHA-256 | `8359cfae11498886927e5d2325351ae4beee9ff8833a683eeb7ad182960eab0d` |

`rv-0016` was accepted as a source-grounded oddity: MITRE ATT&CK itself maps
M1027 Password Policies to T1599.001, and the target quotes the supplied
mitigation without claiming deployment. The sign-off authorizes training on
these reviewed bytes; it does not authorize deployment or the GPU launch
itself.

```bash
uv run python finetuning/prepare_review_pack.py \
  --dataset .vera/datasets/vera-domain-v4.zip \
  --output .vera/review/v4-review-20261111
```

The output directory is local and ignored. It contains:

| File | Purpose |
| --- | --- |
| `REVIEW.md` | human-readable cases, claims, evidence excerpts and automated checks |
| `cases.jsonl` | the same cases with `review.verdict`, `reviewer`, `notes` fields to fill |
| `review.csv` | a spreadsheet view with blank verdict columns |
| `report.json` | selection counts and any failed automated check |
| `signoff.json` | reviewer, date and the human training authorization |

Automated checks cover schema, citations, exact factual quotes, scope, intent, alerts
and the runtime contract. The reviewer must still decide whether the claims are right
and whether the summary overstates local impact. After completing the pack, run:

```bash
uv run python finetuning/prepare_review_pack.py --summarize .vera/review/v4-review-20261111
```

`ready_for_authorization` is true only when every case is accepted, every `fix`/`reject`
has notes and a reviewer is recorded. The summarizer reports `human_reviewed: true` and
`signoff_authorized: true` after this sign-off, but it never sets
`training_authorized` itself: that requires an explicit change to the generated
dataset and a new audit.

The authorized derivative keeps the reviewed data files byte-for-byte, changes only the
manifest authorization fields, records the reviewed manifest SHA-256 and the review-pack
hashes, and adds `AUTHORIZATION.md`. It is written to a new directory so the reviewed
artifact stays immutable. `AUTHORIZATION.md` lists the reviewer, date, verdicts and
hashes; `token-budget.json` binds the authorized manifest SHA-256 to the 2,560-token
preflight.

## Build and inspect

```bash
uv run python finetuning/vera_domain/cli.py \
  --snapshots .vera/datasets/public-snapshots-v1 \
  --output .vera/datasets/vera-domain-v4
```

The command only builds data and refuses to overwrite an existing directory or archive.
The ZIP and extracted directory remain local, ignored artifacts. Choose a fresh output
for a replacement candidate and obtain a new review, authorization and token preflight.
