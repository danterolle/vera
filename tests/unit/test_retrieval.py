from vera.retrieval.corpus import LocalCorpus
from vera.retrieval.cve import extract_cve_ids
from vera.retrieval.embeddings import HashEmbedder
from vera.retrieval.knowledge import CuratedKnowledge


def test_curated_knowledge_finds_concept() -> None:
    knowledge = CuratedKnowledge()
    results = knowledge.search("What is defense in depth?")
    assert results[0].title == "Defense in depth"
    assert knowledge.supports("Why is defense in depth useful?")
    assert not knowledge.supports("How does zero trust work?")
    assert not knowledge.supports("What is defense evasion?")
    assert not knowledge.supports("What is risk?")


def test_corpus_finds_exact_cve() -> None:
    results = LocalCorpus(HashEmbedder()).search("CVE-2021-44228", limit=2)
    assert any("CVE-2021-44228" in item.title for item in results)


def test_hybrid_corpus_covers_multiple_authoritative_domains() -> None:
    corpus = LocalCorpus(HashEmbedder())
    assert corpus.status().total_documents >= 60
    assert corpus.search("OS credential dumping T1003", limit=1)[0].title.startswith("T1003")
    assert corpus.search("SQL injection CWE-89", limit=1)[0].title.startswith("CWE-89")
    assert "Zero Trust" in corpus.search("NIST zero trust architecture", limit=1)[0].title
    scores = corpus.search("path traversal", limit=1)[0].metadata
    assert {"retrieval_score", "lexical_score", "vector_score"} <= scores.keys()


def test_cve_extraction_is_normalized_and_unique() -> None:
    assert extract_cve_ids("cve-2024-3094 and CVE-2024-3094") == ["CVE-2024-3094"]
