---
name: vera-workflow-dev
description: >-
  Develop or debug VERA's LangGraph nodes, routing, ReAct loop and human review.
---

# Workflow changes

Read [architecture](../../../docs/architecture.md) and
[`graph.py`](../../../src/vera/workflow/graph.py).
State fields belong in `domain/state.py` and must be initialized by the workflow.
Nodes return partial updates and append meaningful trace entries.

Keep original request identifiers, citation failures and model/tool budgets intact.
Never replace rejected claims with unrelated quotations or bypass a required review.
Use `reasoning/review.py` for deterministic review triggers and
[review operations](../../../docs/chat.md#human-review) for decision semantics.
