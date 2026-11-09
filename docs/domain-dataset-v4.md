# VERA v4 public-evidence domain dataset

This is the v4 candidate for teaching VERA's evidence-based defensive analysis contract.
It is generated from **real, pinned public records** plus repository-bundled official
snapshots and explicit synthetic analyst scenarios. Generation loads no model weights,
calls no external language model and trains nothing.

The package is a **candidate**, not an approved training corpus:
`training_authorized` and `human_reviewed` remain `false` until a human reviews it.

## Why v4 exists

The v1 candidate matched an older runtime prompt and had narrow coverage. The v3 adapter
showed the practical gaps: it refused in-domain unknown concepts, answered social turns
as security questions, and only saw replays with zero or one alert. v4 rebuilds the data
against the **current** runtime prompts and extends all of those dimensions.

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

The KEV snapshot is catalog `2026.10.21`. Neither source is presented as a current API
result. Only official JSON records are used. `licenses/` retains the upstream notices.
Every fragment records its source URL, original field, selected verbatim text, field path,
snapshot revision and download hash.

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

- Targets are deterministic, source-grounded scenarios, not expert SOC decisions or human annotations.
- Traffic is controlled simulation, not production telemetry.
- Social, clarification and language variants are authored templates, not observed users.
- Sources are frozen snapshots, not live vulnerability intelligence.
- Passing the audit only shows internal consistency; it does not prove model improvement.
- Do not train or deploy without a human review, explicit consent and a Kaggle compatibility run.

## Build and inspect

```bash
uv run python finetuning/vera_domain/cli.py \
  --snapshots .vera/datasets/public-snapshots-v1 \
  --output .vera/datasets/vera-domain-v4
```

The command is data-only. It refuses to overwrite an existing directory or archive.
The visible `vera-domain-v4.zip` and the extracted directory are local, ignored artifacts.
