import json

from vera.knowledge_graph.models import GraphView
from vera.knowledge_graph.search import resolve_entities, search_entities
from vera.knowledge_graph.store import KnowledgeGraphError, KnowledgeGraphStore

LABELS = {
    "has_weakness": "has weakness",
    "subtechnique_of": "subtechnique of",
    "part_of": "belongs to tactic",
    "mitigates": "mitigates",
    "uses": "uses",
    "child_of": "specializes",
    "exploits_weakness": "targets weakness",
    "covers": "covers topic",
    "includes_weakness": "includes weakness",
}


def source_info(key, raw, field=None, quote=None) -> dict:
    record = json.loads(raw)
    return {
        "id": key,
        "label": record["title"],
        "kind": "source",
        "url": record.get("url"),
        "status": record["status"],
        "content": record["content"],
        "metadata": record["metadata"],
        "field_path": field,
        "supporting_quote": quote,
    }


def graph_view(
    store: KnowledgeGraphStore, identifier: str | None, limit: int, *, provenance: bool = False
) -> GraphView:
    view = GraphView(status=store.status(), provenance=provenance)
    if not view.status.available:
        return view
    limit = min(max(limit, 1), 100)
    try:
        with store.connection() as conn:
            ids = resolve_entities(conn, identifier) if identifier else []
            if identifier and not ids:
                ids = [item["id"] for item in search_entities(conn, identifier, 8)]
            view.selected_ids = ids
            if identifier and not ids:
                return view
            nodes, edges = {}, {}
            rows = conn.execute(
                "MATCH (a:Assertion)-[:SUBJECT]->(s:Entity), "
                "(a)-[:OBJECT]->(t:Entity), (a)-[p:SUPPORTED_BY]->(r:SourceRecord) "
                "WHERE $overview OR s.id IN $ids OR t.id IN $ids "
                "RETURN a.id, a.predicate, a.status, s.id, s.kind, s.name, "
                "t.id, t.kind, t.name, r.record_key, r.payload_json, "
                "p.field_path, p.supporting_quote ORDER BY a.id LIMIT $limit",
                {"overview": not identifier, "ids": ids, "limit": limit + 1},
            ).get_all()
            view.truncated = len(rows) > limit
            for row in rows[:limit]:
                (
                    aid,
                    predicate,
                    status,
                    sid,
                    skind,
                    sname,
                    tid,
                    tkind,
                    tname,
                    key,
                    raw,
                    field,
                    q,
                ) = row
                nodes.setdefault(sid, {"id": sid, "label": sname, "kind": skind, "sources": []})
                nodes.setdefault(tid, {"id": tid, "label": tname, "kind": tkind, "sources": []})
                source = source_info(key, raw, field, q)
                if provenance:
                    nodes[key] = source
                    nodes[aid] = {
                        "id": aid,
                        "label": LABELS.get(predicate, predicate),
                        "kind": "assertion",
                        "status": status,
                        "sources": [source],
                    }
                    for target, label in ((sid, "SUBJECT"), (tid, "OBJECT"), (key, "SUPPORTED_BY")):
                        edges[aid, target, label] = {
                            "source": aid,
                            "target": target,
                            "label": label,
                            "predicate": label,
                            "status": status,
                            "sources": [source],
                        }
                else:
                    edge = edges.setdefault(
                        (sid, tid, predicate),
                        {
                            "source": sid,
                            "target": tid,
                            "label": LABELS.get(predicate, predicate),
                            "predicate": predicate,
                            "status": status,
                            "assertion_ids": [],
                            "sources": [],
                        },
                    )
                    edge["assertion_ids"].append(aid)
                    if not any(item["id"] == key for item in edge["sources"]):
                        edge["sources"].append(source)
            selected = conn.execute(
                "MATCH (e:Entity) WHERE e.id IN $ids RETURN e.id, e.kind, e.name, e.aliases",
                {"ids": list(dict.fromkeys([*ids, *nodes]))},
            ).get_all()
            for eid, kind, name, aliases in selected:
                node = nodes.setdefault(eid, {"id": eid, "sources": []})
                node.update(kind=kind, label=name, aliases=json.loads(aliases or "[]"))
            docs = conn.execute(
                "MATCH (r:SourceRecord)-[:DESCRIBES]->(e:Entity) WHERE e.id IN $ids "
                "RETURN e.id, r.record_key, r.payload_json ORDER BY r.record_key LIMIT $limit",
                {"ids": list(nodes), "limit": limit * 4},
            ).get_all()
            for eid, key, raw in docs:
                source = source_info(key, raw)
                node = nodes[eid]
                if len(node["sources"]) < 4:
                    node["sources"].append(source)
                if provenance:
                    nodes[key] = source
                    edges[key, eid, "DESCRIBES"] = {
                        "source": key,
                        "target": eid,
                        "label": "describes",
                        "predicate": "DESCRIBES",
                        "sources": [source],
                    }
            view.nodes, view.edges = list(nodes.values()), list(edges.values())
    except KnowledgeGraphError as exc:
        view.status.available = False
        view.status.error = str(exc)
    return view
