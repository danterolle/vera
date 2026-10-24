import re
from collections.abc import Callable
from dataclasses import dataclass, field

from vera.domain.enums import Route
from vera.domain.plans import ResourcePlan
from vera.domain.reports import DetectionAlert
from vera.errors import ProviderError
from vera.providers.base import ModelProvider
from vera.retrieval.cve import extract_cve_ids
from vera.retrieval.knowledge import CuratedKnowledge
from vera.retrieval.subjects import WEB_INTENT, research_query

CONCEPT_PATTERN = re.compile(
    r"^(what (?:is|are)|define|explain|describe|how (?:does|do|is|are)|"
    r"why (?:is|are|does)|can you explain|could you explain|tell me about|"
    r"che cos['’]?[eè]|cos['’]?[eè]|cosa [eè]|come funziona|perch[eé]|"
    r"definisci|descrivi|spiega(?:mi)?|puoi spiegare)\b",
    re.IGNORECASE,
)
ATTACK_PATTERN = re.compile(r"\b(mitre|att&ck|t\d{4}(?:\.\d{3})?|technique)\b", re.IGNORECASE)
TECHNIQUE_PATTERN = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
CURRENT_PATTERN = re.compile(
    r"\b(current|latest|recent|today|now|news|novit[àa]|notizie|aggiornament[oi]|"
    r"ultim[oeia]|nuov[oeia]|attual[ei]|recent[ei]|incidente|attacco|campagna|breach|"
    r"epss|kev|nvd|osv|exploited)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RouteDecision:
    plan: ResourcePlan
    reason: str
    model_calls: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def route(self) -> Route:
        return self.plan.route


class Router:
    def __init__(
        self,
        provider: ModelProvider,
        supports_cag: Callable[[str], bool] | None = None,
    ) -> None:
        self.provider = provider
        self.supports_cag = supports_cag or CuratedKnowledge().supports

    def select(
        self,
        query: str,
        has_events: bool,
        alerts: list[DetectionAlert],
        *,
        interpreted: bool = False,
    ) -> RouteDecision:
        cve_ids = sorted(
            set(extract_cve_ids(query))
            | {cve for alert in alerts for cve in alert.cve_ids}
        )
        technique_ids = sorted(
            {item.upper() for item in TECHNIQUE_PATTERN.findall(query)}
            | {alert.technique_id for alert in alerts if alert.technique_id}
        )
        reasons = []
        web_request = bool(WEB_INTENT.search(query))
        attack_request = bool(ATTACK_PATTERN.search(query))
        current_request = bool(CURRENT_PATTERN.search(query))
        use_tools = bool(cve_ids) or web_request or current_request
        use_rag = use_tools or bool(alerts) or attack_request or current_request
        if alerts:
            reasons.append("Deterministic event rules produced alerts.")
        if has_events:
            reasons.append("A normalized event stream was supplied.")
        if cve_ids:
            reasons.append("Exact CVE identifiers require authoritative lookups.")
        if web_request:
            reasons.append("The user explicitly requested online research.")
        if technique_ids:
            reasons.append("ATT&CK identifiers require corpus retrieval.")
        elif attack_request:
            reasons.append("An ATT&CK research request requires corpus retrieval.")
        if current_request and not cve_ids:
            reasons.append("Current context was requested without an exact identifier.")
        plan = ResourcePlan(
            use_rag=use_rag,
            use_tools=use_tools,
            use_stream=has_events or bool(alerts),
            cve_ids=cve_ids,
            technique_ids=technique_ids,
            web_query=(
                research_query(query) if web_request or current_request and not cve_ids else None
            ),
            reasons=reasons,
        )
        if CONCEPT_PATTERN.search(query):
            if not self.supports_cag(query):
                expanded = plan.model_copy(
                    update={
                        "use_rag": True,
                        "reasons": [
                            *plan.reasons,
                            "The concept is not covered by curated knowledge; "
                            "retrieval is required.",
                        ],
                    }
                )
                return self._decision(expanded)
            return self._decision(
                plan.model_copy(
                    update={
                        "reasons": [
                            *plan.reasons,
                            "A stable conceptual question was detected.",
                        ]
                    }
                )
            )
        if has_events or use_rag:
            return self._decision(plan)
        if interpreted:
            return self._decision(plan.model_copy(update={
                "use_rag": not self.supports_cag(query),
                "reasons": ["The conversation model resolved the question before routing."],
            }))
        return self._ambiguous(query, plan)

    def _ambiguous(self, query: str, plan: ResourcePlan) -> RouteDecision:
        if self.provider.external:
            try:
                route = self.provider.classify(query)
                if route in {Route.STREAM, Route.FULL}:
                    raise ProviderError(
                        "The model selected an event-only route without events"
                    )
                if route == Route.CAG_ONLY and not self.supports_cag(query):
                    route = Route.CAG_RAG
                use_rag = route in {Route.CAG_RAG, Route.CAG_RAG_TOOL}
                resolved = plan.model_copy(
                    update={
                        "use_rag": use_rag,
                        "use_tools": route == Route.CAG_RAG_TOOL and bool(plan.cve_ids),
                        "reasons": ["The configured LLM resolved an ambiguous request."],
                    }
                )
                return self._decision(resolved, model_calls=1)
            except ProviderError as exc:
                warning = f"LLM routing failed: {exc}"
        else:
            warning = None
        fallback = plan.model_copy(
            update={
                "use_rag": True,
                "reasons": ["The ambiguous-request fallback selected retrieval."],
            }
        )
        return self._decision(fallback, model_calls=int(warning is not None), warning=warning)

    @staticmethod
    def _decision(
        plan: ResourcePlan,
        *,
        model_calls: int = 0,
        warning: str | None = None,
    ) -> RouteDecision:
        reason = " ".join(plan.reasons) or "Only curated context is required."
        return RouteDecision(plan, reason, model_calls, [warning] if warning else [])
