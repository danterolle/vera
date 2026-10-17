import sys

import pytest

from vera.domain.evidence import make_evidence
from vera.knowledge_graph.projection import record_key
from vera.knowledge_graph.retrieval import search_graph
from vera.knowledge_graph.selection import combine_evidence
from vera.knowledge_graph.store import KnowledgeGraphStore
from vera.providers.composers import _is_current_live
from vera.workflow.evidence import deduplicate_evidence

pytest.importorskip("kuzu")


def test_optional_dependency_failure_is_explicit(settings, monkeypatch):
    graph = KnowledgeGraphStore(
        settings.model_copy(update={"kg_path": settings.db_path.with_suffix(".kuzu")})
    )
    monkeypatch.setitem(sys.modules, "kuzu", None)
    result = search_graph(graph, "T1190")
    assert result.error and "--extra knowledge-graph" in result.error
    assert not graph.path.exists()


def test_incompatible_schema_is_not_silently_modified(settings):
    graph = KnowledgeGraphStore(
        settings.model_copy(update={"kg_path": settings.db_path.with_suffix(".kuzu")})
    )
    graph.build([])
    with graph.connection(write=True) as conn:
        conn.execute("MATCH (m:GraphMeta) SET m.version = 999").close()
    assert not graph.status().available
    assert "schema version" in graph.status().error


def test_graph_cached_api_does_not_replace_fresh_live_lookup():
    fresh = make_evidence(
        "nvd",
        "Current NVD",
        "Current authoritative description.",
        metadata={"cve_id": "CVE-2021-44228", "provenance": "live_api"},
    )
    cached = fresh.model_copy(
        update={
            "id": "ev-kg-cached",
            "metadata": {**fresh.metadata, "kg_record_key": "cached"},
        }
    )
    assert _is_current_live(fresh) and not _is_current_live(cached)
    assert deduplicate_evidence([cached, fresh]) == [fresh]


def test_official_bundled_and_synchronized_records_are_not_current_live_calls():
    for provenance in ("bundled_official_snapshot", "synchronized_feed"):
        record = make_evidence(
            "cisa_kev",
            "KEV snapshot",
            "Original catalog description.",
            metadata={"provenance": provenance},
        )
        assert not _is_current_live(record)


def test_graph_and_lexical_duplicates_share_one_registry_entry():
    lexical = make_evidence(
        "mitre_attack",
        "T1190",
        "Original source description.",
        metadata={"external_id": "T1190", "selection_score": 0.9},
    )
    graph = lexical.model_copy(
        update={
            "id": "ev-kg-original",
            "metadata": {
                "external_id": "T1190",
                "kg_record_key": record_key(lexical),
                "kg_original_evidence_id": lexical.id,
            },
        }
    )
    combined = combine_evidence([graph], [lexical])
    assert len(combined) == 1
    assert combined[0].id == graph.id
    assert combined[0].metadata["selection_score"] == 0.9


def test_upstream_scores_are_preserved_in_source_identity(settings):
    source = make_evidence(
        "nvd",
        "NVD record",
        "Original description.",
        metadata={"cve_id": "CVE-2021-44228", "cvss_score": 9.8},
    )
    graph = KnowledgeGraphStore(
        settings.model_copy(
            update={
                "kg_path": settings.db_path.with_suffix(".kuzu"),
            }
        )
    )
    graph.build([source])
    assert search_graph(graph, "CVE-2021-44228").evidence[0].metadata["cvss_score"] == 9.8
