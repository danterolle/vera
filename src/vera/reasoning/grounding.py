import re

from vera.domain.evidence import Citation, Evidence

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[._:-][a-z0-9]+)*", re.IGNORECASE)
NUMBER_PATTERN = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)*(?:%|ms|s)?(?!\w)",
    re.IGNORECASE,
)
IDENTIFIER_PATTERN = re.compile(
    r"\b(?:CVE-\d{4}-\d{4,19}|CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?)\b",
    re.IGNORECASE,
)
NEGATIONS = {"no", "not", "never", "without", "cannot", "isnt", "doesnt"}
NUMERIC_LABELS = {
    "cvss", "epss", "score", "probability", "percentile", "version",
    "severity", "threshold", "confidence", "ports", "requests", "seconds",
}
COMPARATORS = (
    (re.compile(r"(?:greater than|more than|above|over|>)\s*$"), "gt"),
    (re.compile(r"(?:at least|>=)\s*$"), "gte"),
    (re.compile(r"(?:less than|below|under|<)\s*$"), "lt"),
    (re.compile(r"(?:at most|<=)\s*$"), "lte"),
)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "has", "have", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "their", "this", "to", "was", "were", "which", "with",
}


def grounding_error(
    claim_text: str,
    citation: Citation,
    evidence: Evidence,
    minimum_coverage: float = 0.55,
) -> str | None:
    quote = _normalize(citation.supporting_quote)
    content = _normalize(evidence.content)
    if quote not in content:
        return "supporting quote is not present verbatim in the cited evidence"
    claim_tokens = _tokens(claim_text)
    quote_tokens = _tokens(citation.supporting_quote)
    if not claim_tokens:
        return "claim has no meaningful tokens"
    coverage = len(claim_tokens & quote_tokens) / len(claim_tokens)
    if coverage < minimum_coverage:
        return f"supporting quote covers only {coverage:.0%} of meaningful claim terms"
    missing_identifiers = _values(IDENTIFIER_PATTERN, claim_text) - _values(
        IDENTIFIER_PATTERN,
        citation.supporting_quote,
    )
    if missing_identifiers:
        return f"supporting quote omits identifiers: {', '.join(sorted(missing_identifiers))}"
    missing_numbers = _numeric_facts(claim_text) - _numeric_facts(
        citation.supporting_quote
    )
    if missing_numbers:
        values = ", ".join(sorted(fact[0] for fact in missing_numbers))
        return f"supporting quote omits or contradicts numeric facts: {values}"
    claim_negated = bool(_raw_tokens(claim_text) & NEGATIONS)
    quote_negated = bool(_raw_tokens(citation.supporting_quote) & NEGATIONS)
    if claim_negated != quote_negated:
        return "claim and supporting quote use incompatible negation"
    return None


def quote_is_verbatim(citation: Citation, evidence: Evidence) -> bool:
    return _normalize(citation.supporting_quote) in _normalize(evidence.content)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _raw_tokens(text: str) -> set[str]:
    normalized = text.casefold().replace("'", "").replace("’", "")
    return set(TOKEN_PATTERN.findall(normalized))


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _raw_tokens(text)
        if token not in STOP_WORDS and (len(token) > 2 or token.isdigit())
    }


def _values(pattern: re.Pattern[str], text: str) -> set[str]:
    return {value.upper() for value in pattern.findall(text)}


def _numeric_facts(text: str) -> set[tuple[str, str, tuple[str, ...]]]:
    normalized = _normalize(text)
    facts = set()
    for match in NUMBER_PATTERN.finditer(normalized):
        prefix = normalized[max(0, match.start() - 80) : match.start()]
        segment = re.split(r"[,;]|\band\b", prefix)[-1]
        labels = tuple(
            sorted(
                label
                for label in NUMERIC_LABELS
                if re.search(rf"\b{re.escape(label)}\b", segment)
            )
        )
        comparator = next(
            (value for pattern, value in COMPARATORS if pattern.search(segment)),
            "eq",
        )
        facts.add((match.group().upper(), comparator, labels))
    return facts
