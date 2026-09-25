import httpx

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.errors import SourceError
from vera.sources.base import get_json, unavailable_evidence


class CisaKevSource:
    source = SourceType.CISA_KEV
    url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self._payload: dict | None = None

    def lookup(self, cve_id: str) -> Evidence:
        try:
            if self._payload is None:
                self._payload = get_json(self.client.get(self.url), self.source)
            payload = self._payload
            record = next(
                (
                    item
                    for item in payload.get("vulnerabilities", [])
                    if item.get("cveID", "").upper() == cve_id
                ),
                None,
            )
            if record is None:
                return unavailable_evidence(
                    self.source,
                    cve_id,
                    "The CVE is not present in the current CISA KEV catalog.",
                    self.url,
                )
            content = (
                f"{cve_id} is in CISA KEV as {record.get('vulnerabilityName', 'unnamed')}. "
                f"Added {record.get('dateAdded', 'unknown')}; remediation due "
                f"{record.get('dueDate', 'unknown')}. Required action: "
                f"{record.get('requiredAction', 'not provided')}"
            )
            return make_evidence(
                self.source,
                f"{cve_id} - CISA KEV entry",
                content,
                url=self.url,
                metadata={
                    "cve_id": cve_id,
                    "catalog_version": payload.get("catalogVersion"),
                    "date_added": record.get("dateAdded"),
                    "due_date": record.get("dueDate"),
                    "ransomware_use": record.get("knownRansomwareCampaignUse"),
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"CISA KEV response parsing failed: {exc}") from exc
