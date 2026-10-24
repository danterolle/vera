from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx

from vera.config import Settings
from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.errors import SourceError
from vera.sources.base import SourceLookup, unavailable_evidence
from vera.sources.cisa import CisaKevSource
from vera.sources.cve_org import CveOrgSource
from vera.sources.epss import EpssSource
from vera.sources.nvd import NvdSource
from vera.sources.osv import OsvSource
from vera.sources.web import WebResearch

SOURCE_URLS = {
    SourceType.NVD: "https://services.nvd.nist.gov/rest/json/cves/2.0",
    SourceType.CISA_KEV: CisaKevSource.url,
    SourceType.CVE_ORG: CveOrgSource.base_url,
    SourceType.FIRST_EPSS: EpssSource.url,
    SourceType.OSV: OsvSource.base_url,
}


class SourceHub:
    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self.settings = settings
        self._client_factory = client_factory

    def lookup(self, cve_ids: list[str], *, limit: int | None = None) -> SourceLookup:
        if not cve_ids:
            return SourceLookup([], 0)
        if not self.settings.live_sources:
            evidence = [
                unavailable_evidence(
                    source,
                    cve_id,
                    "Live source access is disabled by configuration.",
                    url,
                )
                for cve_id in cve_ids
                for source, url in SOURCE_URLS.items()
            ]
            return SourceLookup(
                evidence,
                0,
                [
                    "Live source access is disabled; bundled snapshots remain "
                    "identifiable as snapshots."
                ],
            )
        client = self._make_client()
        try:
            adapters = [
                NvdSource(client, _secret(self.settings.nvd_api_key)),
                CisaKevSource(client),
                CveOrgSource(client),
                EpssSource(client),
                OsvSource(client),
            ]
            evidence: list[Evidence] = []
            warnings: list[str] = []
            tasks = [(cve_id, adapter) for cve_id in cve_ids for adapter in adapters]
            call_limit = self.settings.max_tool_calls
            if limit is not None:
                call_limit = min(call_limit, max(0, limit))
            selected = tasks[:call_limit]
            skipped = tasks[call_limit:]
            if selected:
                with ThreadPoolExecutor(
                    max_workers=min(self.settings.source_workers, len(selected))
                ) as executor:
                    futures = [
                        (cve_id, adapter, executor.submit(adapter.lookup, cve_id))
                        for cve_id, adapter in selected
                    ]
                    for cve_id, adapter, future in futures:
                        try:
                            evidence.append(future.result())
                        except (httpx.HTTPError, SourceError) as exc:
                            detail = f"{adapter.source.value} lookup failed: {exc}"
                            warnings.append(detail)
                            evidence.append(
                                unavailable_evidence(
                                    adapter.source,
                                    cve_id,
                                    detail,
                                    SOURCE_URLS[adapter.source],
                                )
                            )
            for cve_id, adapter in skipped:
                item = unavailable_evidence(
                    adapter.source,
                    cve_id,
                    "Lookup skipped because the configured tool-call limit was reached.",
                    SOURCE_URLS[adapter.source],
                )
                evidence.append(
                    item.model_copy(update={"metadata": {**item.metadata, "skipped": True}})
                )
            if skipped:
                warnings.append(
                    f"The tool-call limit was reached; {len(skipped)} lookup(s) were skipped."
                )
            return SourceLookup(evidence, len(selected), warnings)
        finally:
            client.close()

    def _make_client(self) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.Client(
            timeout=self.settings.request_timeout_seconds,
            headers={"User-Agent": "VERA/0.1 (+https://github.com/)"},
            follow_redirects=True,
        )

    def research(self, query: str, *, limit: int, topic: str | None = None) -> SourceLookup:
        if not self.settings.live_sources or not self.settings.web_search_enabled:
            detail = "Online research is disabled by configuration; no HTTP request was made."
            return SourceLookup([
                make_evidence(
                    SourceType.WEB, f"Online research: {query[:200]}", detail,
                    status=EvidenceStatus.UNAVAILABLE,
                )
            ], 0, [detail])
        with self._make_client() as client:
            return WebResearch(client, _secret(self.settings.web_search_api_key)).lookup(
                query, limit, topic=topic,
            )


def _secret(value: object | None) -> str | None:
    return value.get_secret_value() if value is not None else None
