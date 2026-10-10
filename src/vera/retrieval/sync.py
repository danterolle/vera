import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from vera.config import Settings
from vera.domain.enums import SourceType
from vera.errors import SourceError
from vera.retrieval.models import (
    CorpusFeed,
    CorpusSyncReport,
    FeedBatch,
    FeedManifest,
)
from vera.retrieval.normalizers import (
    CISA_KEV_URL,
    normalize_attack,
    normalize_cisa_kev,
)
from vera.retrieval.store import CorpusStore

ATTACK_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
    "master/enterprise-attack/enterprise-attack.json"
)


class CorpusSynchronizer:
    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self.settings = settings
        self.store = CorpusStore(settings.corpus_dir, settings.max_corpus_documents)
        self._client_factory = client_factory

    def sync(self, feed: CorpusFeed = CorpusFeed.ALL) -> CorpusSyncReport:
        selected = (
            [CorpusFeed.MITRE_ATTACK, CorpusFeed.CISA_KEV]
            if feed == CorpusFeed.ALL
            else [feed]
        )
        client = self._make_client()
        try:
            batches = [self._fetch(current, client) for current in selected]
        finally:
            client.close()
        self.store.replace(batches)
        return CorpusSyncReport(
            total_documents=sum(len(batch.evidence) for batch in batches),
            feeds=[batch.manifest for batch in batches],
        )

    def _fetch(self, feed: CorpusFeed, client: httpx.Client) -> FeedBatch:
        if feed == CorpusFeed.MITRE_ATTACK:
            url = ATTACK_URL
            source = SourceType.MITRE_ATTACK
            normalizer = normalize_attack
        elif feed == CorpusFeed.CISA_KEV:
            url = CISA_KEV_URL
            source = SourceType.CISA_KEV
            normalizer = normalize_cisa_kev
        else:
            raise SourceError(f"Unsupported corpus feed: {feed}")
        payload = self._get_json(client, url)
        try:
            evidence, version = normalizer(payload)
        except (TypeError, ValueError) as exc:
            raise SourceError(f"{feed.value} normalization failed: {exc}") from exc
        if not evidence:
            raise SourceError(f"{feed.value} normalization produced no documents")
        return FeedBatch(
            manifest=FeedManifest(
                feed=feed,
                source=source,
                source_url=url,
                version=version,
                documents=len(evidence),
                fetched_at=datetime.now(UTC),
            ),
            evidence=evidence,
        )

    def _get_json(self, client: httpx.Client, url: str) -> dict[str, Any]:
        try:
            content = bytearray()
            with client.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > self.settings.max_feed_bytes:
                        raise SourceError(
                            f"Feed exceeds the {self.settings.max_feed_bytes} byte limit"
                        )
                    content.extend(chunk)
            payload = json.loads(content)
        except httpx.HTTPError as exc:
            raise SourceError(f"Corpus feed request failed: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceError(f"Corpus feed returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise SourceError("Corpus feed returned a non-object JSON response")
        return payload

    def _make_client(self) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.Client(
            timeout=max(self.settings.request_timeout_seconds, 30.0),
            headers={"User-Agent": "VERA/0.1 corpus synchronizer"},
            follow_redirects=True,
        )
