from vera.domain.enums import ClaimStatus, EvidenceStatus, Route, SourceType
from vera.domain.evidence import Citation, Claim, Evidence
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.providers.stream_composer import compose_stream
from vera.retrieval.cve import extract_cve_ids

LIVE_SOURCES = {
    SourceType.CVE_ORG,
    SourceType.NVD,
    SourceType.CISA_KEV,
    SourceType.FIRST_EPSS,
    SourceType.OSV,
}
SOURCE_PRIORITY = {
    SourceType.CVE_ORG: 0,
    SourceType.NVD: 1,
    SourceType.CISA_KEV: 2,
    SourceType.FIRST_EPSS: 3,
    SourceType.OSV: 4,
    SourceType.MITRE_ATTACK: 5,
    SourceType.CWE: 6,
    SourceType.CAPEC: 7,
    SourceType.OWASP: 8,
    SourceType.NIST: 9,
    SourceType.CAG: 10,
}


def compose_deterministic(
    request: AnalysisRequest,
    route: Route,
    evidence: list[Evidence],
    alerts: list[DetectionAlert],
    statistics: StreamStatistics,
) -> GeneratedAnswer:
    if request.events:
        return _stream_answer(request, evidence, alerts, statistics)
    cve_ids = extract_cve_ids(request.query)
    if cve_ids:
        return _vulnerability_answer(cve_ids, evidence)
    selected = _relevant_available(evidence, limit=3 if route == Route.CAG_RAG else 2)
    claims = [_evidence_claim(item) for item in selected]
    if not claims:
        claims = [_empty_claim()]
    if route == Route.CAG_ONLY:
        summary = "The request was answered from stable curated cybersecurity knowledge."
    else:
        sources = ", ".join(sorted({item.source.value for item in selected}))
        summary = f"Retrieved {len(selected)} relevant document(s) from {sources or 'the corpus'}."
    return GeneratedAnswer(summary=summary, claims=claims)


def _vulnerability_answer(
    cve_ids: list[str],
    evidence: list[Evidence],
) -> GeneratedAnswer:
    matching = [
        item
        for item in evidence
        if item.metadata.get("cve_id") in cve_ids and item.source != SourceType.MEMORY
    ]
    available = sorted(
        [item for item in matching if item.status == EvidenceStatus.AVAILABLE],
        key=lambda item: (SOURCE_PRIORITY.get(item.source, 99), item.title),
    )
    unavailable = [item for item in matching if item.status == EvidenceStatus.UNAVAILABLE]
    claims = [_evidence_claim(item) for item in available[:10]]
    if unavailable:
        claims.append(_unavailable_claim(unavailable))
    if not claims:
        claims = [_empty_claim()]
    current = [item.source for item in available if _is_current_live(item)]
    live_count = len(set(current))
    identifiers = ", ".join(cve_ids)
    if live_count:
        summary = (
            f"Analyzed {identifiers} using {live_count} available current authoritative source(s)."
        )
    else:
        summary = (
            f"Analyzed {identifiers} without current live data; any available "
            "bundled record is an explicitly dated snapshot and graph records are cached evidence."
        )
    return GeneratedAnswer(summary=summary, claims=claims)


def _stream_answer(
    request: AnalysisRequest,
    evidence: list[Evidence],
    alerts: list[DetectionAlert],
    statistics: StreamStatistics,
) -> GeneratedAnswer:
    stream = next((item for item in evidence if item.source == SourceType.STREAM), None)
    summary, claims = compose_stream(request, stream, alerts, statistics)
    claims.extend(
        _evidence_claim(item)
        for item in _relevant_available(evidence, limit=3)
        if item.source not in {SourceType.CAG, SourceType.STREAM}
    )
    unavailable = [item for item in evidence if item.status == EvidenceStatus.UNAVAILABLE]
    if unavailable:
        claims.append(_unavailable_claim(unavailable))
    return GeneratedAnswer(summary=summary, claims=claims)


def _relevant_available(evidence: list[Evidence], limit: int) -> list[Evidence]:
    selected = [
        item
        for item in evidence
        if item.status == EvidenceStatus.AVAILABLE
        and item.source not in {SourceType.MEMORY, SourceType.STREAM}
        and not item.metadata.get("fallback", False)
    ]
    selected.sort(
        key=lambda item: (
            0 if item.source in LIVE_SOURCES else 1,
            -float(item.metadata.get("selection_score", item.metadata.get("retrieval_score", 0))),
            SOURCE_PRIORITY.get(item.source, 99),
        )
    )
    return selected[:limit]


def _is_current_live(evidence: Evidence) -> bool:
    return (
        evidence.source in LIVE_SOURCES
        and evidence.metadata.get("provenance") == "live_api"
        and not evidence.metadata.get("snapshot", False)
        and not evidence.metadata.get("kg_record_key")
    )


def _evidence_claim(evidence: Evidence) -> Claim:
    quote = evidence.content[:4000]
    return Claim(
        text=quote,
        status=ClaimStatus.SUPPORTED_FACT,
        evidence_ids=[evidence.id],
        citations=[Citation(evidence_id=evidence.id, supporting_quote=quote)],
    )


def _unavailable_claim(evidence: list[Evidence]) -> Claim:
    sources = ", ".join(sorted({item.source.value for item in evidence}))
    return Claim(
        text=f"Current information was unavailable from: {sources}.",
        status=ClaimStatus.UNAVAILABLE,
        evidence_ids=[item.id for item in evidence],
        citations=[
            Citation(evidence_id=item.id, supporting_quote=item.content[:4000]) for item in evidence
        ],
    )


def _empty_claim() -> Claim:
    return Claim(text="No relevant evidence is available.", status=ClaimStatus.UNAVAILABLE)
