---
name: vera-testing-and-eval
description: >-
  Use this skill when verifying code quality, running benchmark evaluations, validating claim grounding rates,
  or creating synthetic evaluation scenarios in VERA.
---

# VERA Testing & Evaluation Skill

This skill documents how to execute VERA's verification suite, benchmark performance across controlled scenarios, and maintain high evidentiary grounding.

---

## 1. Quick Quality Checks

Before committing or testing complex changes, run the linter and format checker:

```bash
# Code linter
uv run ruff check .

# Format verification
uv run ruff format --check .
```

---

## 2. Benchmark Evaluation (`vera evaluate`)

VERA includes a built-in evaluation framework in `src/vera/evaluation/runner.py` that executes synthetic security scenarios in an isolated temporary environment.

### Run Evaluation
```bash
# Human-readable summary output
uv run vera evaluate

# Structured JSON report
uv run vera evaluate --json
```

### Key Metrics Explained
- **`routing_accuracy`**: Proportion of scenarios where the meta-controller selected the exact expected `Route`. Must be 100%.
- **`retrieval_success_rate`**: Proportion of queries where minimum required source documents were successfully retrieved.
- **`detector_accuracy`**: Accuracy of event stream detectors matching expected alert rules (e.g. `rule:port_scan`, `rule:auth_brute_force`).
- **`grounding_rate`**: Ratio of verified grounded claims against total factual assertions.
- **`average_source_coverage`**: Average percentage of factual claims supported by valid evidence citations.

---

## 3. Adding New Evaluation Scenarios

Scenarios reside in `src/vera/data/evaluation/scenarios.json`:

```json
{
  "name": "cve_and_stream_hybrid",
  "query": "Investigate CVE-2021-44228 alongside the incoming network log.",
  "expected_route": "FULL",
  "minimum_available_sources": 2,
  "events_file": "jndi_injection.jsonl",
  "simulated": true,
  "expected_rules": ["rule:jndi_lookup"]
}
```

### Scenario Fields:
- `name`: Unique scenario identifier.
- `query`: User prompt to execute.
- `expected_route`: One of `CAG_ONLY`, `CAG_RAG`, `CAG_RAG_TOOL`, `STREAM`, `FULL`.
- `minimum_available_sources`: Minimum expected evidence count.
- `events_file`: Optional sample filename in `src/vera/data/samples/`.
- `simulated`: Set to `true` if synthetic event data is used.
- `expected_rules`: List of detection rule IDs expected to fire.

---

## 4. Testing Grounding & Validation Manually

To test whether a citation meets the lexical grounding standard without running full inference:
1. Examine `src/vera/reasoning/grounding.py`.
2. Ensure the citation meets three conditions:
   - Verbatim presence: `citation.supporting_quote` must be an exact substring of `evidence.content`.
   - Token coverage: At least 55% of the meaningful tokens in `claim.claim_text` must be present in `citation.supporting_quote`.
   - Exact values: All CVE/CWE/ATT&CK IDs and numeric facts in the claim must appear in the quote.
