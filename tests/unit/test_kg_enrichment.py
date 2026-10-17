import json

import pytest

from vera.domain.evidence import make_evidence
from vera.knowledge_graph.retrieval import search_graph
from vera.knowledge_graph.schema import STATEMENTS
from vera.knowledge_graph.search import search_entities
from vera.knowledge_graph.store import KnowledgeGraphStore
from vera.knowledge_graph.view import graph_view
from vera.retrieval.resources import load_evidence_directory

kuzu = pytest.importorskip("kuzu")


@pytest.fixture
def graph(settings):
    return KnowledgeGraphStore(
        settings.model_copy(update={"kg_path": settings.db_path.with_suffix(".kuzu")})
    )


def test_reference_names_are_upgraded_without_regressing_or_losing_aliases(graph):
    sub = make_evidence(
        "mitre_attack",
        "PowerShell",
        "PowerShell description.",
        metadata={"external_id": "T1059.001"},
    )
    parent = make_evidence(
        "mitre_attack",
        "Command and Scripting Interpreter",
        "Parent text.",
        metadata={"external_id": "T1059", "aliases": ["Shell interpreters"]},
    )
    graph.build([sub])
    graph.build([parent])
    graph.build([sub])
    with graph.connection() as conn:
        assert conn.execute(
            "MATCH (e:Entity {id:'attack:enterprise:T1059'}) RETURN e.name"
        ).get_next() == [parent.title]
        assert search_entities(conn, "shell interpreters")[0]["id"] == "attack:enterprise:T1059"
    assert search_graph(graph, "Explain PowerShell").seed_ids == ["attack:enterprise:T1059.001"]
    assert not search_graph(graph, "Explain PowerShellish").seed_ids


def test_bundled_graph_has_real_relationships_and_no_isolated_documents(graph):
    documents = load_evidence_directory("knowledge") + load_evidence_directory("corpus")
    first = graph.build(documents)
    assert first.counts["Entity"] >= 100
    assert graph.build(documents).counts == first.counts
    with graph.connection() as conn:
        predicates = {
            row[0]
            for row in conn.execute("MATCH (a:Assertion) RETURN DISTINCT a.predicate").get_all()
        }
        assert {
            "uses",
            "mitigates",
            "part_of",
            "child_of",
            "covers",
            "includes_weakness",
            "exploits_weakness",
            "has_weakness",
            "subtechnique_of",
        } <= predicates
        assert conn.execute(
            "MATCH (s:SourceRecord) WHERE NOT EXISTS {MATCH (s)--()} RETURN count(s)"
        ).get_next() == [0]
    report = search_graph(graph, "Explain Log4Shell")
    assert report.seed_ids == ["CVE-2021-44228"]
    assert "CWE-502" in report.entity_ids
    assert search_graph(graph, "Explain incident response").assertion_ids


def test_semantic_view_aggregates_support_and_keeps_provenance_accessible(graph):
    record = make_evidence(
        "mitre_attack", "PowerShell", "Original source text.", metadata={"external_id": "T1059.001"}
    )
    version = record.model_copy(update={"metadata": {**record.metadata, "attack_version": "2"}})
    graph.build([record, version])
    view = graph_view(graph, "PowerShell", 10)
    assert len(view.edges) == 1
    assert len(view.edges[0]["sources"]) == 2
    assert len(view.edges[0]["assertion_ids"]) == 2
    assert all(node["kind"] == "technique" for node in view.nodes)
    assert graph_view(graph, "not a real topic", 10).nodes == []
    raw = graph_view(graph, "PowerShell", 10, provenance=True)
    assert {node["kind"] for node in raw.nodes} == {"technique", "assertion", "source"}


def test_v1_upgrade_preserves_history_and_connects_older_source_versions(graph):
    original = make_evidence("cag", "Least privilege", "Minimum necessary permissions.")
    db = kuzu.Database(graph.path, buffer_pool_size=64 * 1024 * 1024, max_num_threads=2)
    conn = kuzu.Connection(db)
    try:
        for statement in STATEMENTS:
            legacy = statement.replace("name STRING, aliases STRING", "name STRING").replace(
                "payload_json STRING, title STRING, ", "payload_json STRING, "
            )
            conn.execute(legacy).close()
        conn.execute("CREATE (:GraphMeta {id:'schema',version:1})").close()
        conn.execute("CREATE (:Run {id:'old-run',session_id:'old-session'})").close()
        conn.execute(
            "CREATE (:SourceRecord {record_key:'old',evidence_id:$id,source:'cag', "
            "content:$content,payload_json:$raw})",
            {"id": original.id, "content": original.content, "raw": original.model_dump_json()},
        ).close()
    finally:
        conn.close()
        db.close()
    assert not graph.status().available
    enriched = original.model_copy(
        update={
            "metadata": {
                "graph_entities": [{"id": "concept:least-privilege", "name": "Least privilege"}]
            }
        }
    )
    status = graph.build([enriched])
    assert status.available and status.schema_version == 2 and status.counts["Run"] == 1
    with graph.connection() as conn:
        assert conn.execute(
            "MATCH (r:SourceRecord {record_key:'old'}) RETURN r.title, r.payload_json"
        ).get_next() == [original.title, original.model_dump_json()]
        # NULL URLs are equal for the purpose of sharing descriptive links too.
        assert conn.execute(
            "MATCH (:SourceRecord {record_key:'old'})-[:DESCRIBES]->(e:Entity) RETURN e.id"
        ).get_next() == ["concept:least-privilege"]
        assert json.loads(conn.execute("MATCH (e:Entity) RETURN e.aliases").get_next()[0])
