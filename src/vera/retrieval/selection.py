from dataclasses import dataclass
from datetime import UTC, datetime

from vera.domain.evidence import Evidence
from vera.retrieval.ranking import tokenize


@dataclass(frozen=True)
class ScoredDocument:
    evidence: Evidence
    relevance: float
    lexical: float
    vector: float


def select_documents(
    candidates: list[ScoredDocument],
    limit: int,
    min_score: float,
    *,
    now: datetime | None = None,
) -> list[Evidence]:
    if limit <= 0:
        return []
    current = now or datetime.now(UTC)
    pool = sorted(
        (item for item in candidates if item.relevance >= min_score),
        key=lambda item: (-item.relevance, item.evidence.title, item.evidence.id),
    )[: max(20, limit * 5)]
    selected: list[Evidence] = []
    selected_tokens: list[set[str]] = []
    while pool and len(selected) < limit:
        choices = []
        for candidate in pool:
            tokens = set(tokenize(f"{candidate.evidence.title} {candidate.evidence.content}"))
            similarity = max(
                (_similarity(tokens, previous) for previous in selected_tokens),
                default=0.0,
            )
            if similarity >= 0.9:
                continue
            quality = _quality(candidate.evidence)
            freshness = _freshness(candidate.evidence, current)
            novelty = 1 - similarity
            score = (0.8 * candidate.relevance + 0.12 * quality + 0.08 * freshness) * (
                0.82 + 0.18 * novelty
            )
            choices.append((score, candidate, tokens, quality, freshness, novelty))
        if not choices:
            break
        score, candidate, tokens, quality, freshness, novelty = min(
            choices,
            key=lambda item: (-item[0], item[1].evidence.title, item[1].evidence.id),
        )
        selected.append(
            candidate.evidence.model_copy(
                update={
                    "metadata": {
                        **candidate.evidence.metadata,
                        "retrieval_score": round(candidate.relevance, 4),
                        "lexical_score": round(candidate.lexical, 4),
                        "vector_score": round(candidate.vector, 4),
                        "quality_score": round(quality, 4),
                        "freshness_score": round(freshness, 4),
                        "novelty_score": round(novelty, 4),
                        "selection_score": round(score, 4),
                    }
                }
            )
        )
        selected_tokens.append(tokens)
        pool.remove(candidate)
    return selected


def _quality(evidence: Evidence) -> float:
    if evidence.metadata.get("snapshot"):
        return 0.55
    if evidence.metadata.get("provenance") == "synchronized_feed":
        return 0.95
    return 0.85


def _freshness(evidence: Evidence, now: datetime) -> float:
    for key in ("modified", "snapshot_date", "date_added"):
        value = evidence.metadata.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"Invalid {key} for evidence {evidence.id}: expected an ISO date")
        try:
            published = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid {key} for evidence {evidence.id}: {value}") from exc
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        age_days = max(0, (now - published).total_seconds() / 86_400)
        return max(0.0, 1 - age_days / 730)
    return 0.5


def _similarity(first: set[str], second: set[str]) -> float:
    union = first | second
    return len(first & second) / len(union) if union else 0.0
