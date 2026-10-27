---
name: vera-testing-and-eval
description: >-
  Check VERA's code quality, synthetic evaluation scenarios and claim grounding.
---

# Evaluation

Use the commands in [README development](../../../README.md#development).
Scenarios are in `src/vera/data/evaluation/scenarios.json`;
their schema and metrics are defined in `evaluation/runner.py`.
Use existing sample filenames and detector rule IDs, not invented examples.

The benchmark disables review and live sources. Minimum source coverage counts
distinct source categories, not document rows.
Passing it does not establish live-model accuracy, human-review correctness or GPU fit.
Validate those behaviors separately when the change requires it.
