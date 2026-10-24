import re

from vera.domain.evidence import Evidence
from vera.retrieval.resources import load_evidence_directory

WORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*", re.IGNORECASE)
SINGLE_TOKEN_TOPICS = {
    "cve", "cvss", "cyberattacco", "cyberattack", "malware",
    "ransomware", "phishing", "firewall",
}


class CuratedKnowledge:
    def __init__(self) -> None:
        self.documents = load_evidence_directory("knowledge")

    def search(self, query: str, limit: int = 3) -> list[Evidence]:
        ranked = self._rank(query)
        if not ranked:
            policy = next(
                doc for doc in self.documents if doc.title == "Evidence and inference policy"
            )
            return [
                policy.model_copy(
                    update={"metadata": {**policy.metadata, "fallback": True}}
                )
            ]
        return [document for _, document in ranked[:limit]]

    def supports(self, query: str) -> bool:
        query_lower = query.lower()
        query_tokens = set(WORD_PATTERN.findall(query_lower))
        for document in self.documents:
            keywords = [keyword.lower() for keyword in document.metadata.get("keywords", [])]
            exact_topic = any(
                keyword in query_lower
                and (" " in keyword or keyword in SINGLE_TOKEN_TOPICS)
                for keyword in keywords
            )
            topic_tokens = set(WORD_PATTERN.findall(" ".join(keywords)))
            title_tokens = set(WORD_PATTERN.findall(document.title.lower()))
            distinct = query_tokens & (topic_tokens | title_tokens)
            if exact_topic or len(distinct) >= 2:
                return True
        return False

    def _rank(self, query: str) -> list[tuple[float, Evidence]]:
        query_lower = query.lower()
        query_tokens = set(WORD_PATTERN.findall(query_lower))
        ranked: list[tuple[float, Evidence]] = []
        for document in self.documents:
            keywords = document.metadata.get("keywords", [])
            keyword_tokens = set(WORD_PATTERN.findall(" ".join(keywords)))
            overlap = len(query_tokens & keyword_tokens)
            phrase_hits = sum(2 for keyword in keywords if keyword in query_lower)
            title_hits = len(query_tokens & set(WORD_PATTERN.findall(document.title.lower())))
            score = float(overlap + phrase_hits + title_hits)
            if score:
                ranked.append((score, document))
        ranked.sort(key=lambda item: (-item[0], item[1].title))
        return ranked
