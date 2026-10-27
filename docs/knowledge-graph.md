# Knowledge graph

Kuzu 0.11.3 is an optional embedded domain graph, not the LangGraph workflow engine.
The default database is `.vera/knowledge.kuzu`; no Kuzu server is needed.

## Build and enable

```bash
uv sync --extra dev --extra knowledge-graph
uv run --extra knowledge-graph vera kg-build
uv run --extra knowledge-graph vera kg-status
```

Set `VERA_KG_ENABLED=true` in `.env` and restart VERA to enable retrieval.
Building the database alone does not enable it. `VERA_KG_PATH` changes its location.
Imports are incremental and do not duplicate unchanged source records.
Run `kg-build` again after an explicit `vera corpus-sync`.

## Inspect

Open `/knowledge-graph` on the local VERA server. Search by name, alias or identifier,
for example `PowerShell`, `CWE-89` or `T1059.001`, then inspect neighbors and sources.
This is VERA's local SVG viewer, not Kuzu Explorer.

| Endpoint | Purpose |
| --- | --- |
| `/v1/knowledge-graph/status` | Availability, schema version and counts |
| `/v1/knowledge-graph/search?q=PowerShell` | Name/alias/ID suggestions |
| `/v1/knowledge-graph?id=T1059.001&limit=50` | Bounded neighborhood |
| `/v1/knowledge-graph?id=PowerShell&provenance=true` | Sources and assertions |

```bash
uv run --extra knowledge-graph vera kg-export \
  --id T1059.001 --output /tmp/knowledge-graph.json
```

The export is a bounded view, not a database backup.

## Meaning and provenance

`Entity` holds domain identities. `SourceRecord` holds immutable evidence versions.
An `Assertion` links subject and object entities through a semantic predicate and
retains its supporting source. `Run`, `Alert` and `Event` record analysis context.
The schema and migrations live in
[`schema.py`](../src/vera/knowledge_graph/schema.py).

Examples include `subtechnique_of`, `mitigates`, `uses` and CVE-to-CWE `has_weakness`
relations. Structured mappings remain inferences, not proof of execution or compromise.
Missing edges do not establish negative facts. Conflicting source versions can coexist;
cached API records do not become current live evidence.
Asset inventory, affected-version matching and automatic expiry are not implemented.

## Verify use and handle failures

In an analysis result, inspect `metadata.knowledge_graph`.
`enabled`, `attempted` and `available` describe configuration and retrieval;
`retained_evidence_ids` identifies retained graph records and `cited_evidence_ids`
identifies records actually cited. Availability alone does not prove use in an answer.

`VERA_KG_HOPS`, `VERA_KG_MAX_RESULTS` and `VERA_KG_QUERY_TIMEOUT_MS` bound traversal.
Queries use fixed parameterized templates; models cannot submit arbitrary Cypher.
Unavailable or locked graphs produce explicit warnings and ordinary retrieval continues.
Run projection jobs are committed with SQLite history and retried on later enabled
analyses or `kg-build`.

Use one API worker. Close VERA and other graph writers before backup, migration or
external inspection; never delete or replace an open database.
Keep the pinned Kuzu version unless schema and migration compatibility are checked.
