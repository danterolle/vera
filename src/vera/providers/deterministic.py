from vera.domain.enums import ClaimStatus, EvidenceStatus, Route, SourceType
from vera.domain.evidence import Claim, Evidence
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest

ROUTE_SUMMARIES = {
    Route.CAG_ONLY: "The answer uses stable, curated cybersecurity knowledge.",
    Route.CAG_RAG: "The answer combines curated knowledge with the local evidence corpus.",
    Route.CAG_RAG_TOOL: "The answer combines local context with exact authoritative lookups.",
    Route.STREAM: "The event stream was analyzed with deterministic rules; no attack rule fired.",
    Route.FULL: "The event stream triggered detections and was correlated with retrieved evidence.",
}


class DeterministicProvider:
    name = "deterministic"
    external = False

    def classify(self, query: str) -> Route:
        return Route.CAG_RAG

    def generate(
        self,
        request: AnalysisRequest,
        route: Route,
        evidence: list[Evidence],
        alerts: list[DetectionAlert],
        statistics: StreamStatistics,
        feedback: list[str],
    ) -> GeneratedAnswer:
        claims = [self._claim(item) for item in evidence[:24]]
        if not claims:
            claims.append(
                Claim(
                    text="No relevant evidence was available for this request.",
                    status=ClaimStatus.UNAVAILABLE,
                )
            )
        summary = ROUTE_SUMMARIES[route]
        if alerts:
            summary += (
                f" {len(alerts)} alert(s) were observed across "
                f"{statistics.total_events} event(s); detections do not prove compromise."
            )
        return GeneratedAnswer(summary=summary, claims=claims)

    @staticmethod
    def _claim(evidence: Evidence) -> Claim:
        if evidence.status == EvidenceStatus.UNAVAILABLE:
            status = ClaimStatus.UNAVAILABLE
        elif evidence.status == EvidenceStatus.SIMULATED:
            status = ClaimStatus.SIMULATED
        elif evidence.source in {SourceType.STREAM, SourceType.MEMORY}:
            status = ClaimStatus.SYSTEM_INFERENCE
        else:
            status = ClaimStatus.SUPPORTED_FACT
        return Claim(
            text=_claim_text(evidence.content),
            status=status,
            evidence_ids=[evidence.id],
        )


def _claim_text(content: str) -> str:
    return content if len(content) <= 4000 else f"{content[:3997]}..."
