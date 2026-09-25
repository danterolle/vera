from threading import Lock
from time import sleep

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


def test_tool_budget_creates_explicit_skipped_evidence(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        live_sources=True,
        max_tool_calls=3,
    )
    transport = httpx.MockTransport(handler)
    hub = SourceHub(settings, lambda: httpx.Client(transport=transport))
    result = hub.lookup(["CVE-2021-44228", "CVE-2024-3094"])
    skipped = [item for item in result.evidence if item.metadata.get("skipped")]
    assert result.tool_calls == 3
    assert len(result.evidence) == 10
    assert len(skipped) == 7
    assert any("7 lookup(s) were skipped" in warning for warning in result.warnings)


def test_failed_cisa_feed_fetch_is_shared_across_cves(tmp_path) -> None:
    calls = 0
    lock = Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.host == "www.cisa.gov":
            with lock:
                calls += 1
            sleep(0.02)
            return httpx.Response(503)
        return httpx.Response(404)

    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        live_sources=True,
        max_tool_calls=15,
    )
    transport = httpx.MockTransport(handler)
    hub = SourceHub(settings, lambda: httpx.Client(transport=transport))
    hub.lookup(["CVE-2021-44228", "CVE-2024-3094", "CVE-2026-9999"])
    assert calls == 1
