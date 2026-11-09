# Golden set (draft)

Purpose: measure behavior that target-reproduction packs cannot measure — whether an
answer is grounded and correct for a case whose target was written independently, not
copied from the training distribution.

A case is **not** evidence until a person has reviewed it and set `"reviewed": true`.
Draft cases (`false`) are format examples: the scorer reports them separately and never
counts them as a result. Do not cite draft cases in a report, a slide or a promotion
decision.

## Rules for a real golden set

- 50–60 cases, all 11 VERA tasks, plus scope and social controls.
- Target authored by hand from the cited evidence, not selected from the dataset.
- No exact target and, where possible, no shared entity with the training split.
  `--require-independent-targets` checks the exact-target part only.
- Two-sided scope: in-domain questions must be accepted, unrelated requests rejected,
  social messages answered with no claims and `out_of_scope=false`.
- A second person reviews statuses, citations and forbidden claims before `reviewed: true`.
- Store the reviewed file and the run report with the model, adapter scale and date.

## Case format

One JSON object per line:

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
  "notes": "Draft example; needs evidence-checked target and a second reviewer."
}
```

- `scope`: `in`, `out` or `social`. `out` requires `out_of_scope=true` and no claims;
  `social` requires `out_of_scope=false` and no claims.
- `statuses_any` / `statuses_none` check the claim statuses present in the answer.
- `answer_any` is a list of groups; each group needs at least one alternative, matched
  case-insensitively anywhere in the answer JSON.
- `answer_none` is a list of terms that must not appear.
- `max_claims` defaults to the contract maximum.

## Scoring

```bash
uv run python finetuning/score_golden.py \
  --cases finetuning/golden/cases.jsonl \
  --answers .vera/finetuning/<run>/answers.jsonl
```

The scorer parses the answer JSON, applies the checks and prints pass counts per model.
Add `--include-draft` to see draft behavior; it is still labeled as non-evidence.

These checks are deterministic keyword, status and scope rules. They catch contradictions,
missing claims and wrong scope, but they do not prove semantic correctness or usefulness.
The human review is the actual ground truth; this tool only makes its checks repeatable.
