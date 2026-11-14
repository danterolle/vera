---
name: vera-testing-and-eval
description: >-
  Check VERA's code quality, synthetic evaluation scenarios and claim grounding.
---

# Evaluation

Use the commands in the [development guide](../../../README.md#development).
The scenarios live in `src/vera/data/evaluation/scenarios.json`, with their schema
and metrics defined in `src/vera/evaluation/runner.py`. Refer to existing sample
filenames and detector rule IDs rather than inventing examples.

The benchmark runs with human review and live sources disabled. Its minimum source
coverage counts distinct source categories, not individual documents. A passing result
does not establish live-model accuracy, correct human-review behavior or GPU fit;
check those separately when they are relevant to the change.
