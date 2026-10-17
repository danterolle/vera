import json

from vera.domain.evidence import Evidence
from vera.knowledge_graph.models import GraphRetrieval
from vera.knowledge_graph.normalization import seeds
from vera.knowledge_graph.search import resolve_entities
from vera.knowledge_graph.store import KnowledgeGraphError, KnowledgeGraphStore

NEIGHBORS = """
MATCH (a:Assertion)-[:SUBJECT]->(s:Entity), (a)-[:OBJECT]->(t:Entity),
      (a)-[:SUPPORTED_BY]->(r:SourceRecord)
WHERE (s.id IN $ids OR t.id IN $ids) AND r.status = 'available' AND r.source <> 'memory'
RETURN a.id, s.id, t.id, r.record_key LIMIT $limit
"""
RECORDS = """
MATCH (r:SourceRecord)-[:DESCRIBES]->(e:Entity)
WHERE e.id IN $ids AND r.status = 'available' AND r.source <> 'memory'
RETURN DISTINCT r.record_key, r.payload_json ORDER BY r.record_key LIMIT $limit
"""


def search_graph(store: KnowledgeGraphStore, query: str) -> GraphRetrieval:
    report = GraphRetrieval(seed_ids=seeds(query))
    if not report.seed_ids and len(query.strip()) < 3:
        return report
    report.attempted = True
    limit = store.settings.kg_max_results
    report.hops = store.settings.kg_hops
    try:
        with store.connection() as conn:
            report.seed_ids = resolve_entities(conn, query)
            report.available = True
            if not report.seed_ids:
                return report
            report.attempted = True
            present = conn.execute(
                "MATCH (e:Entity) WHERE e.id IN $ids RETURN e.id ORDER BY e.id",
                {"ids": report.seed_ids},
            ).get_all()
            visited = {row[0] for row in present}
            frontier = sorted(visited)
            source_assertions: dict[str, list[str]] = {}
            for _ in range(report.hops):
                if not frontier:
                    break
                rows = conn.execute(NEIGHBORS, {"ids": frontier, "limit": limit}).get_all()
                next_nodes = set()
                for assertion, subject, target, record_key in rows:
                    source_assertions.setdefault(record_key, []).append(assertion)
                    next_nodes.update((subject, target))
                    if assertion not in report.assertion_ids:
                        report.assertion_ids.append(assertion)
                frontier = sorted(next_nodes - visited)[:limit]
                visited.update(frontier)
            report.entity_ids = sorted(visited)
            # Exact entity documents precede neighboring records; all lists remain bounded.
            direct = conn.execute(RECORDS, {"ids": report.seed_ids, "limit": limit}).get_all()
            supporting = (
                conn.execute(
                    "MATCH (r:SourceRecord) WHERE r.record_key IN $keys "
                    "RETURN r.record_key, r.payload_json ORDER BY r.record_key LIMIT $limit",
                    {"keys": list(source_assertions)[:limit], "limit": limit},
                ).get_all()
                if source_assertions
                else []
            )
            adjacent = (
                conn.execute(
                    RECORDS,
                    {
                        "ids": report.entity_ids,
                        "limit": limit,
                    },
                ).get_all()
                if report.entity_ids
                else []
            )
            records = dict(direct + supporting + adjacent)
            for key, payload in list(records.items())[:limit]:
                original = Evidence.model_validate(json.loads(payload))
                evidence = original.model_copy(
                    update={
                        "id": f"ev-kg-{key[:32]}",
                        "metadata": {
                            **original.metadata,
                            "kg_record_key": key,
                            "kg_original_evidence_id": original.id,
                            "kg_assertion_ids": source_assertions.get(key, []),
                        },
                    }
                )
                report.evidence.append(evidence)
                report.record_keys.append(key)
                report.evidence_ids.append(evidence.id)
        report.available = True
    except KnowledgeGraphError as exc:
        report.error = str(exc)
    return report
