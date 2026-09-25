import httpx

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.errors import SourceError
from vera.sources.base import get_json, unavailable_evidence


class EpssSource:
    source = SourceType.FIRST_EPSS
    url = "https://api.first.org/data/v1/epss"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def lookup(self, cve_id: str) -> Evidence:
        try:
            payload = get_json(self.client.get(self.url, params={"cve": cve_id}), self.source)
            records = payload.get("data", [])
            if not records:
                return unavailable_evidence(
                    self.source,
                    cve_id,
                    "FIRST EPSS returned no probability estimate for this CVE.",
                    self.url,
                )
            record = records[0]
            probability = float(record["epss"])
            percentile = float(record["percentile"])
            content = (
                f"FIRST EPSS estimates a {probability:.4%} probability of exploitation "
                f"within 30 days, at percentile {percentile:.4%}, for {cve_id}. "
                f"Estimate date: {record.get('date', 'unknown')}."
            )
            return make_evidence(
                self.source,
                f"{cve_id} - FIRST EPSS estimate",
                content,
                url=self.url,
                metadata={
                    "cve_id": cve_id,
                    "probability": probability,
                    "percentile": percentile,
                    "date": record.get("date"),
                    "provenance": "live_api",
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"FIRST EPSS response parsing failed: {exc}") from exc
