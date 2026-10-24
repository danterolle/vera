---
name: vera-kg-operations
description: >-
  Use this skill when managing, building, migrating, or querying the Kuzu embedded knowledge graph in VERA,
  including schema definitions, entity normalization, run projections, and graph exports.
---

# VERA Knowledge Graph Operations Skill

This skill documents how to build, query, update, and debug VERA's embedded domain knowledge graph powered by **Kuzu 0.11.3**.

---

## 1. Key Locations

- `src/vera/knowledge_graph/schema.py`: Kuzu DDL statements, schema versioning (`VERSION = 2`), and migration handlers.
- `src/vera/knowledge_graph/store.py`: `KnowledgeGraphStore` database connection lifecycle and transaction management.
- `src/vera/knowledge_graph/models.py`: Pydantic models for graph entities (`EntityRecord`, `AssertionRecord`, `GraphStatus`).
- `src/vera/knowledge_graph/projection.py`: Logic projecting finished analysis runs, alerts, and citations into graph nodes and relations.
- `src/vera/interfaces/knowledge_graph.py`: Typer CLI command handlers (`kg-build`, `kg-status`, `kg-export`).

---

## 2. Standard Operational Runbook

### Build or Rebuild the Graph
Building imports the bundled corpus (ATT&CK techniques, software, CWEs, CAPEC, KEV) and replays any pending projection jobs stored in SQLite:
```bash
uv run --extra knowledge-graph vera kg-build
```

### Inspect Graph Status
Verify that the database is accessible, check node and edge counts, and verify schema version:
```bash
uv run --extra knowledge-graph vera kg-status
```
Expected output structure:
```json
{
  "available": true,
  "node_count": 120,
  "rel_count": 112,
  "projected_runs": 0,
  "schema_version": 2
}
```

### Export Subgraph Neighborhoods
Export a bounded JSON neighborhood for a specific entity (e.g. `PowerShell`, `T1059.001`, `Log4Shell`):
```bash
uv run --extra knowledge-graph vera kg-export --id "PowerShell" --limit 50 --output powershell_subgraph.json
```

---

## 3. Modifying Schema & Migrations

Kuzu DDL statements are defined in `src/vera/knowledge_graph/schema.py`.

### Safe Schema Modification Rules
1. When adding a table or relation, append the `CREATE NODE TABLE` or `CREATE REL TABLE` statement to `STATEMENTS`.
2. Increment `VERSION` (e.g. `VERSION = 3`).
3. Implement an upgrade function (e.g. `upgrade_v2(connection)`) that handles existing databases gracefully.
4. Verify migration logic by running:
   ```bash
   uv run --extra knowledge-graph vera kg-build
   uv run --extra knowledge-graph vera kg-status
   ```

### Troubleshooting Kuzu Locks
- Kuzu is an embedded in-process database. If a previous process crashed while holding a write transaction lock on `.vera/knowledge.kuzu`, ensure all running instances of `vera serve` are stopped before running `kg-build`.
