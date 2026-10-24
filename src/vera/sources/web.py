"""Bounded, read-only online research. Search results alone are never evidence."""

import json
import re
import socket
from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx

from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence, make_evidence
from vera.retrieval.subjects import concept_subject, normalized
from vera.sources.base import SourceLookup

CATALOGS = ("software/", "techniques/enterprise/", "groups/")
PRIMARY_HOSTS = {
    "attack.mitre.org", "cwe.mitre.org", "capec.mitre.org", "www.cisa.gov", "cisa.gov",
    "nvd.nist.gov", "csrc.nist.gov", "owasp.org", "learn.microsoft.com",
    "msrc.microsoft.com", "github.com", "www.rfc-editor.org",
    "en.wikipedia.org", "it.wikipedia.org", "www.bleepingcomputer.com", "bleepingcomputer.com",
    "thehackernews.com", "darkreading.com", "krebsonsecurity.com",
    "www.mandiant.com", "mandiant.com", "www.crowdstrike.com", "crowdstrike.com",
    "www.sentinelone.com", "sentinelone.com", "csirt.gov.it", "www.csirt.gov.it", "cert.europa.eu",
}
MAX_PAGE_BYTES = 2 * 1024 * 1024
CODE = re.compile(r"^(?:[SG]\d{4}|TA?\d{4}(?:\.\d{3})?)$")


class CatalogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "header", "footer", "form", "noscript"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "h1", "h2", "li", "br"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "header", "footer", "form", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def content(self) -> str:
        return "\n".join(
            line for part in "".join(self.parts).splitlines()
            if (line := " ".join(part.split()))
        )[:5000]


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
                    path = code.replace(".", "/")
                    item = make_evidence(
                        SourceType.MITRE_ATTACK, f"{code} - {name}", description[:5000],
                        url=f"https://attack.mitre.org/{kind}/{path}/",
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
        reason = (
            "Online research was attempted but no usable source was found. "
            "The free provider supplies topic summaries and official-site links, "
            "not a complete web index."
        )
        return self._missing(query, reason)

    def _instant_answer(self, subject: str, limit: int) -> list[Evidence]:
        evidence = []
        try:
            payload = json.loads(self._get(
                "https://api.duckduckgo.com/",
                params={"q": subject, "format": "json", "no_html": 1, "no_redirect": 1},
            ))
            title = str(payload.get("Heading") or subject)[:300]
            text = str(payload.get("AbstractText") or "").strip()
            url = str(payload.get("AbstractURL") or "")
            if text and _public_url(url):
                evidence.append(make_evidence(
                    SourceType.WEB, title, text[:5000], url=url,
                    metadata={
                        "provenance": "live_api", "research_subject": title,
                        "lookup_method": "duckduckgo_instant_answer",
                        "retrieved_from": "https://api.duckduckgo.com/",
                        "upstream_source": payload.get("AbstractSource"),
                        "http_requests": list(self.requests),
                        "scope_validated": True,
                    },
                ))
            for result in payload.get("Results", [])[:2]:
                if len(self.requests) >= limit:
                    break
                url = str(result.get("FirstURL") or "")
                if not _public_url(url):
                    continue
                try:
                    parser = PageText()
                    parser.feed(self._get(url))
                    content = parser.content()
                    if content:
                        evidence.insert(0, make_evidence(
                            SourceType.WEB, title + " — official site", content, url=url,
                            metadata={
                                "provenance": "live_api", "research_subject": title,
                                "lookup_method": "duckduckgo_official_page",
                                "http_requests": list(self.requests),
                                "scope_validated": True,
                            },
                        ))
                except (httpx.HTTPError, ValueError) as exc:
                    self.errors.append(f"Official-site retrieval failed: {exc}")
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            self.errors.append(f"Online topic search failed: {exc}")

        # If Instant Answer returned no results, use web search fallback
        if not evidence and len(self.requests) < limit:
            try:
                from urllib.parse import unquote
                item = {"url": "https://html.duckduckgo.com/html/", "status_code": None}
                self.requests.append(item)
                resp = self.client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": subject},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    follow_redirects=True,
                )
                item["status_code"] = resp.status_code
                if resp.status_code == 200:
                    matches = re.finditer(
                        r'<a class="result__url" href="([^"]+)"[^>]*>([^<]+)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>',
                        resp.text, re.DOTALL,
                    )
                    for match in matches:
                        if len(evidence) >= 2 or len(self.requests) >= limit:
                            break
                        raw_url = match.group(1)
                        m = re.search(r"uddg=([^&]+)", raw_url)
                        actual_url = unquote(m.group(1)) if m else raw_url
                        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
                        if not snippet or not _public_url(actual_url):
                            continue
                        parsed = urlsplit(actual_url)
                        evidence.append(make_evidence(
                            SourceType.WEB, f"{subject} — {parsed.hostname}", snippet[:5000],
                            url=actual_url,
                            metadata={
                                "provenance": "live_api", "research_subject": subject,
                                "lookup_method": "duckduckgo_web_search",
                                "retrieved_from": "https://html.duckduckgo.com/html/",
                                "http_requests": list(self.requests),
                                "scope_validated": True,
                            },
                        ))
            except Exception as exc:
                self.errors.append(f"Web fallback search failed: {exc}")

        return evidence

    def _get(self, url: str, *, params=None, headers=None) -> str:
        item = {"url": url, "status_code": None}
        self.requests.append(item)
        with self.client.stream(
            "GET", url, params=params, headers=headers, follow_redirects=True,
        ) as response:
            item["status_code"] = response.status_code
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_PAGE_BYTES:
                    raise ValueError("Online source exceeds the page-size limit")
            return content.decode("utf-8", errors="replace")

    def _search(self, subject: str, limit: int) -> list[Evidence]:
        evidence = []
        try:
            payload = json.loads(self._get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": subject, "count": 5},
                headers={"X-Subscription-Token": self.api_key},
            ))
            for result in payload.get("web", {}).get("results", []):
                if len(self.requests) >= limit or len(evidence) >= 2:
                    break
                url = str(result.get("url", ""))
                parsed = urlsplit(url)
                if (parsed.scheme != "https" or parsed.hostname not in PRIMARY_HOSTS
                        or parsed.username or parsed.password or parsed.port not in {None, 443}):
                    continue
                parser = PageText()
                try:
                    parser.feed(self._get(url))
                    content = parser.content()
                    if not content:
                        continue
                    evidence.append(make_evidence(
                        SourceType.WEB, str(result.get("title") or subject)[:300], content,
                        url=url, metadata={
                            "provenance": "live_api", "research_subject": subject,
                            "lookup_method": "brave_search_primary_page",
                            "http_requests": list(self.requests),
                        },
                    ))
                except (httpx.HTTPError, ValueError) as exc:
                    self.errors.append(f"Online page retrieval failed: {exc}")
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            self.errors.append(f"Web search failed: {exc}")
        return evidence

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


def _public_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in {None, 443} or len(url) > 2000):
            return False
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ip_address(row[4][0]).is_global for row in addresses)
    except (ValueError, OSError):
        return False
