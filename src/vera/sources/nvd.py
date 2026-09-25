import httpx

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.errors import SourceError
from vera.sources.base import get_json, unavailable_evidence


class NvdSource:
    source = SourceType.NVD
    api_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    detail_url = "https://nvd.nist.gov/vuln/detail/"

    def __init__(self, client: httpx.Client, api_key: str | None = None) -> None:
        self.client = client
        self.api_key = api_key

    def lookup(self, cve_id: str) -> Evidence:
        headers = {"apiKey": self.api_key} if self.api_key else None
        try:
            response = self.client.get(
                self.api_url,
                params={"cveId": cve_id},
                headers=headers,
            )
            payload = get_json(response, self.source)
            records = payload.get("vulnerabilities", [])
            if not records:
                return unavailable_evidence(
                    self.source,
                    cve_id,
                    "NVD returned no matching vulnerability record.",
                    f"{self.detail_url}{cve_id}",
                )
            record = records[0]["cve"]
            description = next(
                (
                    item["value"]
                    for item in record.get("descriptions", [])
                    if item.get("lang") == "en"
                ),
                "No English description is present in the NVD record.",
            )
            score, severity, vector = _cvss(record.get("metrics", {}))
            score_text = (
                f" CVSS {score} ({severity}); vector {vector}." if score is not None else ""
            )
            content = (
                f"{record['id']}: {description}{score_text} "
                f"Published {record.get('published', 'unknown')}; "
                f"last modified {record.get('lastModified', 'unknown')}."
            )
            return make_evidence(
                self.source,
                f"{cve_id} - NVD record",
                content,
                url=f"{self.detail_url}{cve_id}",
                metadata={
                    "cve_id": cve_id,
                    "cvss_score": score,
                    "severity": severity,
                    "vector": vector,
                    "last_modified": record.get("lastModified"),
                    "provenance": "live_api",
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"NVD response parsing failed: {exc}") from exc


def _cvss(metrics: dict) -> tuple[float | None, str | None, str | None]:
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        values = metrics.get(key, [])
        if not values:
            continue
        data = values[0].get("cvssData", {})
        return data.get("baseScore"), data.get("baseSeverity"), data.get("vectorString")
    return None, None, None
