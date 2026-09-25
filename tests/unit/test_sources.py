import httpx

from vera.config import Settings
from vera.domain.enums import EvidenceStatus, SourceType
from vera.sources.hub import SourceHub


def test_source_hub_parses_authoritative_responses(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "services.nvd.nist.gov":
            return httpx.Response(
                200,
                json={
                    "vulnerabilities": [
                        {
                            "cve": {
                                "id": "CVE-2021-44228",
                                "descriptions": [{"lang": "en", "value": "Description"}],
                                "published": "2021-12-10",
                                "lastModified": "2026-01-01",
                                "metrics": {
                                    "cvssMetricV31": [
                                        {
                                            "cvssData": {
                                                "baseScore": 10.0,
                                                "baseSeverity": "CRITICAL",
                                                "vectorString": "CVSS:3.1/test",
                                            }
                                        }
                                    ]
                                },
                            }
                        }
                    ]
                },
            )
        if host == "www.cisa.gov":
            return httpx.Response(
                200,
                json={
                    "catalogVersion": "test",
                    "vulnerabilities": [
                        {
                            "cveID": "CVE-2021-44228",
                            "vulnerabilityName": "Test entry",
                            "dateAdded": "2021-12-10",
                            "dueDate": "2021-12-24",
                            "requiredAction": "Patch",
                        }
                    ],
                },
            )
        if host == "api.first.org":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "epss": "0.9",
                            "percentile": "0.99",
                            "date": "2026-01-01",
                        }
                    ]
                },
            )
        if host == "cveawg.mitre.org":
            return httpx.Response(
                200,
                json={
                    "cveMetadata": {
                        "state": "PUBLISHED",
                        "cveId": "CVE-2021-44228",
                        "assignerShortName": "apache",
                        "datePublished": "2021-12-10",
                        "dateUpdated": "2026-01-01",
                    },
                    "containers": {
                        "cna": {
                            "descriptions": [{"lang": "en", "value": "CNA description"}],
                            "affected": [{"vendor": "Apache", "product": "Log4j"}],
                            "problemTypes": [
                                {"descriptions": [{"description": "CWE-20"}]}
                            ],
                            "references": [{"url": "https://example.test/advisory"}],
                        }
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "CVE-2021-44228",
                "details": "OSV details",
                "aliases": ["GHSA-test"],
                "modified": "2026-01-01",
            },
        )

    settings = Settings(db_path=tmp_path / "db.sqlite", live_sources=True)
    transport = httpx.MockTransport(handler)
    hub = SourceHub(settings, lambda: httpx.Client(transport=transport))
    result = hub.lookup(["CVE-2021-44228"])
    assert result.tool_calls == 5
    assert {item.source for item in result.evidence} == {
        SourceType.NVD,
        SourceType.CISA_KEV,
        SourceType.CVE_ORG,
        SourceType.FIRST_EPSS,
        SourceType.OSV,
    }
    assert all(item.status == EvidenceStatus.AVAILABLE for item in result.evidence)


def test_offline_sources_are_explicitly_unavailable(settings) -> None:
    result = SourceHub(settings).lookup(["CVE-2021-44228"])
    assert result.tool_calls == 0
    assert len(result.evidence) == 5
    assert all(item.status == EvidenceStatus.UNAVAILABLE for item in result.evidence)
