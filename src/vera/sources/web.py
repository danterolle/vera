"""Bounded, read-only research. Search results locate pages; they are never evidence."""

import json
import re

import httpx

from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.retrieval.subjects import concept_subject, normalized
from vera.sources.base import SourceLookup
from vera.sources.web_access import primary_url
from vera.sources.web_content import CatalogParser, PageText, SearchLinks

CATALOGS = ("software/", "techniques/enterprise/", "groups/")
MAX_PAGE_BYTES = 2 * 1024 * 1024
CODE = re.compile(r"^(?:[SG]\d{4}|TA?\d{4}(?:\.\d{3})?)$")


class WebResearch:
    def __init__(self, client: httpx.Client, api_key: str | None = None) -> None:
        self.client = client
        self.api_key = api_key
        self.requests: list[dict] = []
        self.errors: list[str] = []

    def lookup(self, query: str, limit: int, *, topic: str | None = None) -> SourceLookup:
        subject = topic or concept_subject(query) or query.strip()
        if not subject or limit <= 0:
            return self._missing(query, "Online research skipped: no subject or tool budget.")
        if self.api_key and limit >= 2:
            evidence = self._search(query, limit)
            if evidence:
                return SourceLookup(evidence, len(self.requests), self.errors)
        if len(self.requests) < limit:
            evidence = self._instant_answer(subject, limit)
            if evidence:
                return SourceLookup(evidence, len(self.requests), self.errors)
        for catalog in CATALOGS:
            if len(self.requests) >= limit:
                break
            url = f"https://attack.mitre.org/{catalog}"
            try:
                parser = CatalogParser()
                parser.feed(self._get(url))
                parent_code = ""
                for cells in parser.rows:
                    if cells and re.fullmatch(r"T\d{4}", cells[0]):
                        parent_code = cells[0]
                    if (len(cells) >= 4 and not cells[0]
                            and re.fullmatch(r"\.\d{3}", cells[1]) and parent_code):
                        cells = [parent_code + cells[1], *cells[2:]]
                    if len(cells) < 3 or not CODE.fullmatch(cells[0]):
                        continue
                    code, name, description = cells[0], cells[1], cells[-1]
                    aliases = [name]
                    if catalog != "techniques/enterprise/":
                        aliases += [alias.strip() for alias in cells[2].split(",") if alias.strip()]
                    if normalized(subject) not in {normalized(x) for x in [code, *aliases]}:
                        continue
                    kind = catalog.split("/")[0]
                    item = make_evidence(
                        SourceType.MITRE_ATTACK, f"{code} - {name}", description[:5000],
                        url=f"https://attack.mitre.org/{kind}/{code.replace('.', '/')}/",
                        metadata={
                            "external_id": code, "aliases": aliases,
                            "provenance": "live_api", "research_subject": subject,
                            "lookup_method": "mitre_attack_online_catalog",
                            "scope_validated": True,
                            "retrieved_from": url, "http_requests": list(self.requests),
                        },
                    )
                    return SourceLookup([item], len(self.requests), self.errors)
            except (httpx.HTTPError, ValueError) as exc:
                self.errors.append(f"Online ATT&CK lookup failed: {exc}")
        return self._missing(
            query,
            "Online research was attempted but no usable source page or catalog record was found.",
        )

    def _instant_answer(self, subject: str, limit: int) -> list[Evidence]:
        candidates = []
        try:
            payload = json.loads(self._get(
                "https://api.duckduckgo.com/",
                params={"q": subject, "format": "json", "no_html": 1, "no_redirect": 1},
            ))
            title = str(payload.get("Heading") or subject)[:300]
            candidates = [(str(payload.get("AbstractURL") or ""), title)]
            candidates += [
                (str(item.get("FirstURL") or ""), title)
                for item in payload.get("Results", [])[:2]
            ]
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            self.errors.append(f"Online topic search failed: {exc}")
        evidence = self._pages(candidates, subject, "duckduckgo_primary_page", limit)
        if evidence or len(self.requests) >= limit:
            return evidence
        try:
            parser = SearchLinks()
            parser.feed(self._get("https://html.duckduckgo.com/html/", params={"q": subject}))
            return self._pages(
                [(url, subject) for url in parser.urls],
                subject, "duckduckgo_primary_page", limit,
            )
        except (httpx.HTTPError, ValueError) as exc:
            self.errors.append(f"Web fallback search failed: {exc}")
            return []

    def _search(self, subject: str, limit: int) -> list[Evidence]:
        try:
            payload = json.loads(self._get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": subject, "count": 5},
                headers={"X-Subscription-Token": self.api_key},
            ))
            candidates = [
                (str(item.get("url") or ""), str(item.get("title") or subject)[:300])
                for item in payload.get("web", {}).get("results", [])
            ]
            return self._pages(candidates, subject, "brave_search_primary_page", limit)
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            self.errors.append(f"Web search failed: {exc}")
            return []

    def _pages(
        self, candidates: list[tuple[str, str]], subject: str, method: str, limit: int,
    ) -> list[Evidence]:
        evidence = []
        for url, title in list(dict.fromkeys(candidates))[:5]:
            if len(self.requests) >= limit or len(evidence) >= 2:
                break
            if not primary_url(url):
                continue
            try:
                parser = PageText()
                parser.feed(self._get(url))
                content = parser.content()
                if content:
                    evidence.append(make_evidence(
                        SourceType.WEB, title[:300], content, url=url, metadata={
                            "provenance": "live_api", "research_subject": subject,
                            "lookup_method": method, "retrieved_from": url,
                            "http_requests": list(self.requests),
                        },
                    ))
            except (httpx.HTTPError, ValueError) as exc:
                self.errors.append(f"Online page retrieval failed: {exc}")
        return evidence

    def _get(self, url: str, *, params=None, headers=None) -> str:
        item = {"url": url, "status_code": None}
        self.requests.append(item)
        with self.client.stream(
            "GET", url, params=params, headers=headers, follow_redirects=False,
        ) as response:
            item["status_code"] = response.status_code
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_PAGE_BYTES:
                    raise ValueError("Online source exceeds the page-size limit")
            return content.decode("utf-8", errors="replace")

    def _missing(self, query: str, reason: str) -> SourceLookup:
        item = make_evidence(
            SourceType.WEB, f"Online research: {query[:200]}", reason,
            status=EvidenceStatus.UNAVAILABLE,
            metadata={
                "research_query": query, "http_requests": list(self.requests),
                "lookup_method": "online_research_unavailable",
            },
        )
        return SourceLookup([item], len(self.requests), [*self.errors, reason])
