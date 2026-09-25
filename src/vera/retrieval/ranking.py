import math
import re
from collections import Counter

from vera.domain.evidence import Evidence

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", re.IGNORECASE)
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "in",
    "is",
    "of",
    "on",
    "the",
    "this",
    "to",
    "what",
    "with",
}


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token.lower() not in STOP_WORDS
    ]


class Bm25Ranker:
    def __init__(self, documents: list[Evidence]) -> None:
        self.tokens = [tokenize(_searchable_text(document)) for document in documents]
        self.average_length = (
            sum(map(len, self.tokens)) / len(self.tokens) if self.tokens else 0.0
        )
        self.frequencies = [Counter(tokens) for tokens in self.tokens]
        self.document_frequency = Counter(
            token for tokens in self.tokens for token in set(tokens)
        )

    def scores(self, query: str) -> list[float]:
        query_tokens = set(tokenize(query))
        return [
            self._score(tokens, frequencies, query_tokens)
            for tokens, frequencies in zip(
                self.tokens,
                self.frequencies,
                strict=True,
            )
        ]

    def _score(
        self,
        tokens: list[str],
        frequencies: Counter[str],
        query_tokens: set[str],
    ) -> float:
        if not tokens or not self.tokens:
            return 0.0
        score = 0.0
        for token in query_tokens:
            count = frequencies[token]
            if not count:
                continue
            frequency = self.document_frequency[token]
            inverse = math.log(1 + (len(self.tokens) - frequency + 0.5) / (frequency + 0.5))
            denominator = count + 1.5 * (
                0.25 + 0.75 * len(tokens) / max(self.average_length, 1.0)
            )
            score += inverse * count * 2.5 / denominator
        return score


def normalize(scores: list[float]) -> list[float]:
    maximum = max(scores, default=0.0)
    return [score / maximum if maximum > 0 else 0.0 for score in scores]


def _searchable_text(document: Evidence) -> str:
    keywords = " ".join(map(str, document.metadata.get("keywords", [])))
    identifiers = " ".join(
        str(document.metadata.get(key, ""))
        for key in ("cve_id", "external_id", "technique_id", "cwe_id")
    )
    return f"{document.title} {document.content} {keywords} {identifiers}"
