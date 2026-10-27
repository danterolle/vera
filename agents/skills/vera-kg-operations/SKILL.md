---
name: vera-kg-operations
description: >-
  Build, inspect or change VERA's embedded Kuzu graph, migrations and projections.
---

# Knowledge graph operations

Follow [graph operations](../../../docs/knowledge-graph.md).
Implementation lives in `src/vera/knowledge_graph/`; use `schema.py` for migrations,
`store.py` for connections and `projection.py` for retained runs.

Keep Kuzu pinned unless compatibility is checked. Preserve source versions and
provenance; graph associations must not become unsupported factual claims.
Queries use bound parameters and fixed templates.
Back up a closed database before schema work; do not delete an open database to fix a lock.
Inspect actual `kg-status` output rather than assuming counts or field names.
