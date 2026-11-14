# Golden set (draft)

The golden set asks a different question from the template-based evaluation packs:
can VERA give a grounded, correct answer when the expected result was written
independently rather than selected from its training distribution?

A case becomes evaluation evidence only after a person reviews it and sets
`"reviewed": true`. The draft cases included here are examples of the format, not
results that can be cited in a report, presentation or deployment decision.

## Rules for a real golden set

Aim for 50-60 independently written cases covering all 18 dataset tasks, with scope
and social controls. Write each target from its cited evidence rather than copying
a dataset answer. Exclude exact training targets and, where practical, shared training
entities. The packer's `--require-independent-targets` option checks exact-target
novelty, not independent authorship.

Scope checks need both directions: accept cybersecurity questions, reject unrelated
requests and answer social messages without claims or `out_of_scope=true`. Before
marking a case reviewed, have a second person check its statuses, citations and
forbidden assertions. Retain the reviewed cases and run report with the model,
adapter scale and date.

## Case format

Store one JSON object per line. A draft might look like this:

```json
{
  "id": "golden-0001",
  "task": "vulnerability_triage",
  "query": "Explain SQL injection and how to prevent it.",
  "expect": {
    "scope": "in",
    "statuses_any": ["supported_fact"],
    "statuses_none": ["unavailable"],
    "answer_any": [["sql injection"], ["parameterized", "prepared statement"]],
    "answer_none": ["cross site scripting", "xss"],
    "max_claims": 6
  },
  "reviewed": false,
  "reviewer": null,
  "reviewed_at": null,
  "notes": "Draft example; needs evidence-checked target and a second reviewer."
}
```

| Expectation | Meaning |
| --- | --- |
| `scope` | `in`, `out` or `social`; `out` requires rejection without claims, while `social` requires no claims and `out_of_scope=false` |
| `statuses_any`, `statuses_none` | Required alternatives and forbidden claim statuses |
| `answer_any` | Groups of alternatives; each group needs a case-insensitive match in summary or claim text, not just citation metadata |
| `answer_none` | Terms that must not appear in the summary or claim text |
| `max_claims` | Claim limit, bounded by the contract maximum |

## Scoring

```bash
uv run python finetuning/score_golden.py \
  --cases finetuning/golden/cases.jsonl \
  --answers .vera/finetuning/<run>/answers.jsonl
```

Each answer row needs `id`, `model` and the raw JSON string in `answer`. When claims
cite evidence, include the records actually supplied to the model. For served answers,
also retain runtime `metadata`, `warnings` and `http_status`: a fallback or pending
HTTP `202` draft cannot pass as a completed model answer.

The scorer rejects duplicate model/case rows and unknown IDs. Missing answers fail
rather than disappearing from the denominator. It checks the raw six-claim contract
before scope normalization, validates citations and reports passes per model.
Evidence eligibility requires at least 50 reviewed cases across all 18 tasks, with
a named reviewer, an ISO review date and no draft inclusion. Use `--include-draft`
only to inspect draft behavior; the output remains labeled as non-evidence.

These are repeatable keyword, status and scope checks, not a semantic judge. They can
catch missing findings, some contradictions and wrong scope, but cannot establish
correctness or usefulness on their own. Human review supplies the ground truth.
