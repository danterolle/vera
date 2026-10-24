---
name: vera-workflow-dev
description: >-
  Use this skill when developing, refactoring, or debugging VERA's LangGraph workflow nodes,
  state transitions (GraphState), routing logic, the ReAct execution loop, or human-in-the-loop review checkpoints.
---

# VERA Workflow Development Skill

This skill guides you through modifying or extending the core LangGraph workflow topology, state nodes, and execution policies in VERA.

---

## 1. Relevant Code Files

- `src/vera/domain/state.py`: The `GraphState` typed dictionary.
- `src/vera/workflow/graph.py`: Graph definition (`build_graph`), node additions, and conditional edges.
- `src/vera/workflow/nodes.py`: Node implementations (`initialize`, `route`, `generate`, `validate`, `reflection`, `finalize`).
- `src/vera/workflow/acquisition.py`: Context acquisition branches (`cag`, `rag`, `tools`, `stream`, `full`).
- `src/vera/workflow/react.py`: ReAct decision (`react_decide`) and execution (`react_execute`) nodes.
- `src/vera/workflow/review.py`: Human review pause node (`review_wait`) and review assessment (`review_assess`).

---

## 2. Procedure: Adding or Modifying a Workflow Node

### Step 1: Update State Contract (if adding new fields)
If the new node requires or produces new state keys:
1. Open `src/vera/domain/state.py`.
2. Add the field with explicit typing to `GraphState`.
3. In `WorkflowNodes.initialize` (`src/vera/workflow/nodes.py`), initialize the key with a safe default value.

### Step 2: Implement the Node Method
Nodes in VERA are methods on an orchestrator class (e.g. `WorkflowNodes`, `ContextAcquirer`, `ReviewNodes`).
- Input signature: `(self, state: GraphState) -> dict`
- The return dictionary must contain **only the updated keys** (partial state update).
- Always append diagnostic actions to `trace`:
  ```python
  def my_custom_node(self, state: GraphState) -> dict:
      # Perform logic...
      return {
          "custom_key": new_value,
          "trace": state["trace"] + ["custom_action:completed"],
      }
  ```

### Step 3: Wire into LangGraph
1. Open `src/vera/workflow/graph.py`.
2. Register the node:
   ```python
   graph.add_node("my_node", nodes.my_custom_node)
   ```
3. Update edge transitions:
   - For direct transition: `graph.add_edge("previous_node", "my_node")`
   - For conditional routing: update `graph.add_conditional_edges(...)`

### Step 4: Validate Workflow Compilation & Linting
Run ruff to verify type cleanliness and run an offline analysis:
```bash
uv run ruff check src/vera/workflow/
uv run --extra knowledge-graph vera analyze "Explain PowerShell" --offline --json
```

---

## 3. Handling Conditional Human Review

If you are modifying review triggers:
1. Inspect `src/vera/reasoning/review.py`.
2. Review triggers must be **deterministic**:
   - Check `state["alerts"]` for severity `>= HIGH`.
   - Check `state["reflection"].unsupported_claims > 0`.
   - Check that query CVEs exist in `state["evidence"]`.
3. Never bypass `review_wait` when `state["review_required"]` is `True`.
