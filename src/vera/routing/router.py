import re
from dataclasses import dataclass, field

from vera.domain.enums import Route
from vera.errors import ProviderError
from vera.providers.base import ModelProvider
from vera.retrieval.cve import extract_cve_ids

CONCEPT_PATTERN = re.compile(
    r"^(what is|what are|define|explain|describe|che cos[eè]|definisci|spiega)\b",
    re.IGNORECASE,
)
ATTACK_PATTERN = re.compile(r"\b(mitre|att&ck|t\d{4}(?:\.\d{3})?|technique)\b", re.IGNORECASE)
CURRENT_PATTERN = re.compile(
    r"\b(current|latest|recent|today|epss|kev|nvd|osv|exploited|attuale|recente)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: str
    model_calls: int = 0
    warnings: list[str] = field(default_factory=list)


class Router:
    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider

    def select(self, query: str, has_events: bool, has_alerts: bool) -> RouteDecision:
        if has_alerts:
            return RouteDecision(Route.FULL, "Deterministic event rules produced alerts.")
        if has_events:
            return RouteDecision(Route.STREAM, "A normalized event stream was supplied.")
        if extract_cve_ids(query):
            return RouteDecision(Route.CAG_RAG_TOOL, "An exact CVE identifier was detected.")
        if ATTACK_PATTERN.search(query):
            return RouteDecision(Route.CAG_RAG, "A MITRE ATT&CK concept was detected.")
        if CURRENT_PATTERN.search(query):
            return RouteDecision(
                Route.CAG_RAG,
                "Current information was requested without an exact lookup identifier.",
            )
        if CONCEPT_PATTERN.search(query):
            return RouteDecision(Route.CAG_ONLY, "A stable conceptual question was detected.")
        if self.provider.external:
            try:
                route = self.provider.classify(query)
                if route in {Route.STREAM, Route.FULL}:
                    raise ProviderError("The model selected an event-only route without events")
                return RouteDecision(route, "The configured LLM resolved an ambiguous request.", 1)
            except ProviderError as exc:
                return RouteDecision(
                    Route.CAG_RAG,
                    "The ambiguous-request fallback selected retrieval.",
                    1,
                    [f"LLM routing failed: {exc}"],
                )
        return RouteDecision(
            Route.CAG_RAG,
            "No deterministic rule matched; safe retrieval fallback selected.",
        )
