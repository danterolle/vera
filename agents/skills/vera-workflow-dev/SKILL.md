---
name: vera-workflow-dev
description: >-
  Develop or debug VERA's LangGraph nodes, routing, ReAct loop and human review.
---

# Workflow changes

Before changing the workflow, read the [architecture guide](../../../docs/architecture.md)
and [`graph.py`](../../../src/vera/workflow/graph.py). Define state fields in
`domain/state.py` and initialize them in the workflow. Nodes should return partial
updates and add trace entries that explain meaningful transitions.

Preserve the request's original identifiers, citation failures and model/tool budgets.
Never replace a rejected claim with an unrelated quotation or bypass a required review.
Put deterministic review triggers in `reasoning/review.py`, and follow the
[review guide](../../../docs/chat.md#human-review) for decision semantics.
