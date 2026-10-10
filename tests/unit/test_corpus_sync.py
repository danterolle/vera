import httpx

from vera.domain.enums import SourceType
from vera.retrieval.corpus import LocalCorpus
from vera.retrieval.embeddings import HashEmbedder
from vera.retrieval.models import CorpusFeed
from vera.retrieval.store import CorpusStore
from vera.retrieval.sync import CorpusSynchronizer


def test_authoritative_feeds_are_normalized_and_persisted(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(
                200,
                json={
                    "objects": [
                        {
                            "type": "x-mitre-collection",
                            "x_mitre_version": "19.2",
                        },
                        {
                            "type": "attack-pattern",
                            "id": "attack-pattern--test",
                            "name": "Test Technique",
                            "description": "Technique description",
                            "modified": "2026-01-01",
                            "external_references": [
                                {
                                    "source_name": "mitre-attack",
                                    "external_id": "T9999",
                                    "url": "https://attack.mitre.org/techniques/T9999/",
                                }
                            ],
                            "x_mitre_platforms": ["Linux"],
                        },
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "catalogVersion": "2026.01.01",
                "vulnerabilities": [
                    {
                        "cveID": "CVE-2026-9999",
                        "vulnerabilityName": "Test vulnerability",
                        "shortDescription": "Known exploited test record.",
                        "requiredAction": "Apply vendor guidance.",
                        "vendorProject": "Vendor",
                        "product": "Product",
                        "dateAdded": "2026-01-01",
                        "dueDate": "2026-01-22",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    synchronizer = CorpusSynchronizer(
        settings,
        lambda: httpx.Client(transport=transport),
    )
    report = synchronizer.sync(CorpusFeed.ALL)
    assert report.total_documents == 2
    assert {item.version for item in report.feeds} == {"19.2", "2026.01.01"}

    store = CorpusStore(settings.corpus_dir, settings.max_corpus_documents)
    persisted = store.load()
    assert {item.source for item in persisted} == {
        SourceType.MITRE_ATTACK,
        SourceType.CISA_KEV,
    }
    corpus = LocalCorpus(HashEmbedder(), store)
    assert corpus.status().synchronized_documents == 2
    assert corpus.search("T9999 Test Technique", limit=1)[0].title.startswith("T9999")
