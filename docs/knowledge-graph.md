# Knowledge graph

VERA can use Kuzu 0.11.3 as an embedded graph of cybersecurity entities and evidence.
This domain graph is separate from the LangGraph workflow engine. It needs no server
and stores its database at `.vera/knowledge.kuzu` by default.

## Build and enable

```bash
uv sync --extra dev --extra knowledge-graph
uv run --extra knowledge-graph vera kg-build
uv run --extra knowledge-graph vera kg-status
```

Once the database is built, set `VERA_KG_ENABLED=true` in `.env` and restart VERA to
use it for retrieval. Building it alone does not enable the feature. Set `VERA_KG_PATH`
if you need another location. Imports are incremental, so unchanged source records
are not duplicated. Run `kg-build` again after refreshing feeds with `vera corpus-sync`.

## Inspect

Open `/knowledge-graph` on the local VERA server and search for a name, alias or
identifier such as `PowerShell`, `CWE-89` or `T1059.001`. You can then inspect nearby
entities and their sources. This is VERA's SVG viewer, not Kuzu Explorer.

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

The export contains a bounded neighborhood; use a database backup if you need to
preserve the complete graph.

## Meaning and provenance

An `Entity` represents a domain identity, while a `SourceRecord` preserves an immutable
version of evidence. An `Assertion` connects subject and object entities through a
semantic predicate and retains the source behind that connection. `Run`, `Alert` and
`Event` provide the analysis context. The schema and its migrations live in
[`schema.py`](../src/vera/knowledge_graph/schema.py).

Relations include `subtechnique_of`, `mitigates`, `uses` and CVE-to-CWE `has_weakness`.
These mappings do not prove execution or compromise, and a missing edge does not
establish a negative fact. Conflicting source versions can coexist; cached API records
are still cached evidence, not fresh lookups. Asset inventory, affected-version matching
and automatic expiry are not implemented.

## Verify use and handle failures

To see whether an answer used the graph, inspect `metadata.knowledge_graph`.
The `enabled`, `attempted` and `available` fields describe configuration and retrieval.
Compare `retained_evidence_ids` with `cited_evidence_ids` to distinguish records that
were kept from those actually cited. Availability alone does not establish use.

`VERA_KG_HOPS`, `VERA_KG_MAX_RESULTS` and `VERA_KG_QUERY_TIMEOUT_MS` bound traversal.
Queries use fixed parameterized templates; models cannot submit arbitrary Cypher.
Unavailable or locked graphs produce explicit warnings and ordinary retrieval continues.
Run projection jobs are committed with SQLite history and retried on later enabled
analyses or `kg-build`.

Use one API worker, and close VERA and any other graph writers before a backup,
migration or external inspection. Never delete or replace an open database. Keep
the pinned Kuzu version until schema and migration compatibility have been checked.
