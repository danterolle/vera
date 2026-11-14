---
name: vera-kg-operations
description: >-
  Build, inspect or change VERA's embedded Kuzu graph, migrations and projections.
---

# Knowledge graph operations

Start with the [graph operations guide](../../../docs/knowledge-graph.md).
The implementation is in `src/vera/knowledge_graph/`: migrations belong in `schema.py`,
connections in `store.py`, and retained-run projection in `projection.py`.

Keep Kuzu pinned until compatibility has been checked. Preserve source versions and
provenance, and do not turn graph associations into unsupported factual claims. Use
fixed query templates with bound parameters.

Before changing the schema, close the database and back it up. Never delete an open
database to work around a lock. Read the actual `kg-status` output instead of assuming
its field names or record counts.
