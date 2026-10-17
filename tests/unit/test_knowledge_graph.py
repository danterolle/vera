import pytest

from vera.domain.enums import EvidenceStatus
from vera.domain.evidence import make_evidence
from vera.knowledge_graph.normalization import seeds
from vera.knowledge_graph.retrieval import search_graph
from vera.knowledge_graph.store import KnowledgeGraphError, KnowledgeGraphStore
from vera.retrieval.normalizers import normalize_attack

pytest.importorskip("kuzu")


@pytest.fixture
def graph(settings):
    return KnowledgeGraphStore(
        settings.model_copy(update={"kg_path": settings.db_path.with_suffix(".kuzu")})
    )


def record(identifier, **metadata):
    return make_evidence(
        "mitre_attack",
        f"{identifier} fixture",
        f"Original description of {identifier}.",
        metadata={"external_id": identifier, **metadata},
    )


def linked(subject, target, predicate="uses", **metadata):
    return record(
        subject,
        graph_relations=[
            {
                "subject": subject,
                "object": target,
                "predicate": predicate,
                "field_path": "STIX.fixture",
                **metadata,
            }
        ],
    )


def test_idempotent_import_and_closed_handles(graph):
    first = graph.build([record("T1059.001"), record("T1059")])
    second = graph.build([record("T1059.001"), record("T1059")])
    assert first.counts == second.counts
    assert second.counts["Assertion"] == 1
    # A distinct store can reopen the same file after the first has finished.
    assert KnowledgeGraphStore(graph.settings).status().available


def test_two_hops_recover_original_evidence_and_keep_mappings_inferred(graph):
    original = record("T1190")
    graph.build([linked("G0001", "S0001"), linked("S0001", "T1190"), original])
    first = search_graph(graph, "Explain G0001")
    assert "attack:enterprise:T1190" not in first.entity_ids
    graph.settings = graph.settings.model_copy(update={"kg_hops": 2})
    second = search_graph(graph, "Explain G0001")
    assert "attack:enterprise:T1190" in second.entity_ids
    retrieved = next(item for item in second.evidence if item.content == original.content)
    assert retrieved.metadata["kg_original_evidence_id"] == original.id
    with graph.connection() as conn:
        rows = conn.execute("MATCH (a:Assertion) RETURN DISTINCT a.status").get_all()
    assert rows == [["system_inference"]]


def test_metadata_versions_are_distinct_but_repeat_retrieval_is_not(graph):
    one = record("T1190", attack_version="1")
    two = one.model_copy(update={"metadata": {**one.metadata, "attack_version": "2"}})
    assert graph.build([one, two]).counts["SourceRecord"] == 2
    retrieved = search_graph(graph, "T1190")
    assert len(set(retrieved.evidence_ids)) == 2
    assert graph.build(retrieved.evidence).counts["SourceRecord"] == 2


def test_unavailable_and_memory_do_not_support_traversal(graph):
    missing = linked("G0001", "T1190").model_copy(update={"status": EvidenceStatus.UNAVAILABLE})
    memory = make_evidence("memory", "Prior result", "T1190", metadata={"technique_id": "T1190"})
    report = graph.build([missing, memory])
    assert report.counts["Assertion"] == 0
    assert report.counts["SourceRecord"] == 1
    assert search_graph(graph, "G0001").evidence == []


def test_invalid_quote_rolls_back_whole_import(graph):
    graph.build([record("T1190")])
    bad = linked("G0001", "T1190", supporting_quote="This quotation was never in the source.")
    with pytest.raises(KnowledgeGraphError, match="quotation"):
        graph.build([record("T1110"), bad])
    assert graph.status().counts["SourceRecord"] == 1


def test_no_identifier_unknown_identifier_and_query_injection(graph):
    graph.build([record("T1190")])
    unresolved = search_graph(graph, "Explain cybersecurity")
    assert unresolved.attempted and unresolved.available and not unresolved.seed_ids
    unknown = search_graph(graph, "T9999")
    assert unknown.attempted and unknown.available and not unknown.evidence
    assert search_graph(graph, "T1190' DELETE e //").evidence
    assert graph.status().counts["Entity"] == 1
    assert seeds("cve-2021-44228 T1190 T1190") == ["CVE-2021-44228", "attack:enterprise:T1190"]


def test_missing_database_is_reported_without_creating_it(graph):
    result = search_graph(graph, "T1190")
    assert result.attempted and not result.available and "kg-build" in result.error
    assert not graph.path.exists()


def test_limits_bound_records_and_seed_count(graph):
    graph.build([record("T1190", attack_version=str(index)) for index in range(5)])
    graph.settings = graph.settings.model_copy(update={"kg_max_results": 2})
    assert len(search_graph(graph, "T1190").evidence) == 2
    assert len(seeds(" ".join(f"T{index:04}" for index in range(20)))) == 8


def test_attack_sync_preserves_relationships_tactics_and_revocation(graph):
    def node(kind, stix, code, **extra):
        return {
            "type": kind,
            "id": stix,
            "name": code,
            "description": f"Original {code} text.",
            "external_references": [
                {
                    "source_name": "mitre-attack",
                    "external_id": code,
                    "url": "https://attack.mitre.org/",
                }
            ],
            **extra,
        }

    documents, _ = normalize_attack(
        {
            "objects": [
                node("course-of-action", "mitigation--1", "M0001"),
                node(
                    "attack-pattern",
                    "technique--1",
                    "T1190",
                    kill_chain_phases=[
                        {
                            "kill_chain_name": "mitre-attack",
                            "phase_name": "initial-access",
                        }
                    ],
                ),
                node("x-mitre-tactic", "tactic--1", "TA0001", x_mitre_shortname="initial-access"),
                {
                    "type": "relationship",
                    "id": "relationship--1",
                    "relationship_type": "mitigates",
                    "source_ref": "mitigation--1",
                    "target_ref": "technique--1",
                    "description": "Original mapping.",
                },
                {
                    "type": "relationship",
                    "relationship_type": "uses",
                    "revoked": True,
                    "source_ref": "mitigation--1",
                    "target_ref": "technique--1",
                },
            ]
        }
    )
    assert len(documents) == 4
    graph.build(documents)
    report = search_graph(graph, "T1190")
    assert {"attack:enterprise:M0001", "attack:enterprise:TA0001"} <= set(report.entity_ids)
    assert any(item.content == "Original mapping." for item in report.evidence)


def test_cve_weakness_uses_only_explicit_source_fields(graph):
    cve = make_evidence(
        "nvd",
        "Vulnerability",
        "CWE-79 is mentioned but not a mapping.",
        metadata={"cve_id": "CVE-2021-44228", "cwes": ["CWE-502"]},
    )
    graph.build([cve])
    result = search_graph(graph, "CVE-2021-44228")
    assert "CWE-502" in result.entity_ids and "CWE-79" not in result.entity_ids
