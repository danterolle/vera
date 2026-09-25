from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import make_evidence
from vera.workflow.evidence import deduplicate_evidence


def test_live_cve_record_replaces_matching_snapshot() -> None:
    snapshot = make_evidence(
        SourceType.NVD,
        "Snapshot",
        "Old record",
        metadata={"cve_id": "CVE-2021-44228", "snapshot": True},
    )
    live = make_evidence(
        SourceType.NVD,
        "Live",
        "Current record",
        metadata={"cve_id": "CVE-2021-44228"},
    )
    assert deduplicate_evidence([snapshot, live]) == [live]


def test_snapshot_remains_when_live_source_is_unavailable() -> None:
    snapshot = make_evidence(
        SourceType.NVD,
        "Snapshot",
        "Old record",
        metadata={"cve_id": "CVE-2021-44228", "snapshot": True},
    )
    unavailable = make_evidence(
        SourceType.NVD,
        "Unavailable",
        "Live lookup failed",
        status=EvidenceStatus.UNAVAILABLE,
        metadata={"cve_id": "CVE-2021-44228"},
    )
    assert deduplicate_evidence([snapshot, unavailable]) == [snapshot, unavailable]


def test_live_record_replaces_synchronized_record_for_same_source() -> None:
    synchronized = make_evidence(
        SourceType.CISA_KEV,
        "Synchronized",
        "Cached catalog record",
        metadata={
            "cve_id": "CVE-2021-44228",
            "provenance": "synchronized_feed",
        },
    )
    live = make_evidence(
        SourceType.CISA_KEV,
        "Live",
        "Current catalog record",
        metadata={"cve_id": "CVE-2021-44228", "provenance": "live_api"},
    )
    assert deduplicate_evidence([synchronized, live]) == [live]


def test_deduplication_preserves_retrieval_order() -> None:
    first = make_evidence(SourceType.NIST, "First", "Most relevant")
    second = make_evidence(SourceType.CWE, "Second", "Less relevant")
    assert deduplicate_evidence([first, second]) == [first, second]
