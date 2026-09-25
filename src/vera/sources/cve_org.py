import httpx

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.errors import SourceError
from vera.sources.base import get_json, unavailable_evidence


class CveOrgSource:
    source = SourceType.CVE_ORG
    base_url = "https://cveawg.mitre.org/api/cve/"
    record_url = "https://www.cve.org/CVERecord?id="

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def lookup(self, cve_id: str) -> Evidence:
        api_url = f"{self.base_url}{cve_id}"
        response = self.client.get(api_url)
        if response.status_code == 404:
            return unavailable_evidence(
                self.source,
                cve_id,
                "The official CVE Record API returned no matching record.",
                f"{self.record_url}{cve_id}",
            )
        try:
            payload = get_json(response, self.source)
            metadata = payload["cveMetadata"]
            cna = payload.get("containers", {}).get("cna", {})
            description = _english_description(cna.get("descriptions", []))
            products = _affected_products(cna.get("affected", []))
            weaknesses = _weaknesses(cna.get("problemTypes", []))
            state = str(metadata.get("state", "UNKNOWN"))
            content = (
                f"{cve_id} is an official CVE List V5 record in state {state}. "
                f"{description} Affected products reported by the CNA: "
                f"{', '.join(products) or 'not provided'}. "
                f"Weaknesses: {', '.join(weaknesses) or 'not provided'}."
            )[:11_900]
            return make_evidence(
                self.source,
                f"{cve_id} - official CVE record",
                content,
                url=f"{self.record_url}{cve_id}",
                metadata={
                    "cve_id": cve_id,
                    "state": state,
                    "assigner": metadata.get("assignerShortName"),
                    "date_published": metadata.get("datePublished"),
                    "date_updated": metadata.get("dateUpdated"),
                    "products": products,
                    "weaknesses": weaknesses,
                    "references": [
                        item.get("url")
                        for item in cna.get("references", [])[:20]
                        if item.get("url")
                    ],
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"CVE Record response parsing failed: {exc}") from exc


def _english_description(descriptions: list[dict]) -> str:
    return next(
        (
            str(item["value"])
            for item in descriptions
            if item.get("lang", "").lower().startswith("en") and item.get("value")
        ),
        "No English description is present in the official CVE record.",
    )


def _affected_products(affected: list[dict]) -> list[str]:
    products = []
    for item in affected[:20]:
        vendor = str(item.get("vendor") or "unknown vendor")
        product = str(item.get("product") or "unknown product")
        products.append(f"{vendor} {product}")
    return products


def _weaknesses(problem_types: list[dict]) -> list[str]:
    return sorted(
        {
            str(item["description"])
            for group in problem_types
            for item in group.get("descriptions", [])
            if item.get("description")
        }
    )
