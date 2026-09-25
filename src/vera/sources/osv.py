import httpx

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.errors import SourceError
from vera.sources.base import get_json, unavailable_evidence


class OsvSource:
    source = SourceType.OSV
    base_url = "https://api.osv.dev/v1/vulns/"

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def lookup(self, cve_id: str) -> Evidence:
        url = f"{self.base_url}{cve_id}"
        response = self.client.get(url)
        if response.status_code == 404:
            return unavailable_evidence(
                self.source,
                cve_id,
                "OSV returned no record for this CVE identifier.",
                url,
            )
        try:
            payload = get_json(response, self.source)
            details = str(payload.get("details") or "No details are present in the OSV record.")
            aliases = ", ".join(payload.get("aliases", [])[:10]) or "none"
            content = (
                f"{payload.get('id', cve_id)}: {details[:1800]} "
                f"Aliases: {aliases}. Modified: {payload.get('modified', 'unknown')}."
            )
            return make_evidence(
                self.source,
                f"{cve_id} - OSV record",
                content,
                url=url,
                metadata={
                    "cve_id": cve_id,
                    "aliases": payload.get("aliases", []),
                    "modified": payload.get("modified"),
                    "published": payload.get("published"),
                    "provenance": "live_api",
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"OSV response parsing failed: {exc}") from exc
