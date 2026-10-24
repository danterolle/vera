import time

from langgraph.types import interrupt

from vera.domain.review import ReviewDecision
from vera.domain.state import GraphState
from vera.errors import ProviderError
from vera.reasoning.review import review_reasons
from vera.retrieval.subjects import WEB_INTENT, concept_subject, research_query
from vera.workflow.acquisition import ContextAcquirer
from vera.workflow.evidence import deduplicate_evidence
from vera.workflow.runtime import Runtime


class ReviewNodes:
    def __init__(self, runtime: Runtime, *, enabled: bool = True) -> None:
        self.runtime = runtime
        self.enabled = enabled

    def assess(self, state: GraphState) -> dict:
        reasons = review_reasons(state) if self.enabled else []
        if state.get("revision_error"):
            reasons.insert(0, f"Revision failed: {state['revision_error']}")
        if state.get("review_required") and not reasons:
            reasons.append("A revised draft requires a human decision.")
        required = bool(reasons)
        return {
            "review_required": required,
            "review_reasons": reasons,
            "active_ms": (
                state.get("active_ms", 0.0)
                + (time.perf_counter() - state["started_at"]) * 1000
                if required else state.get("active_ms", 0.0)
            ),
        }

    def wait(self, state: GraphState) -> dict:
        decision = ReviewDecision.model_validate(
            interrupt({"run_id": state["run_id"], "reasons": state["review_reasons"]})
        )
        return {
            "review_action": decision.action,
            "review_feedback": decision.feedback or "",
            "revision_count": state.get("revision_count", 0)
            + int(decision.action == "revise"),
            "revision_error": None,
            "started_at": time.perf_counter(),
            "trace": state["trace"] + [f"review:{decision.action}"],
        }

    def revise(self, state: GraphState) -> dict:
        provider = self.runtime.provider
        if not provider.external:
            raise ValueError("Revision requires an external model provider")
        # A human revision is a new evidence pass, not just a paraphrase of the draft.
        plan = state["resource_plan"]
        if WEB_INTENT.search(state["review_feedback"]):
            query = research_query(state["review_feedback"])
            explicit_topic = bool(query)
            if not query:
                request = state["request"]
                query = plan.search_query or research_query(request.query, request.conversation)
            plan = plan.model_copy(update={
                "use_rag": True, "use_tools": True, "web_query": query,
                **({"subject": concept_subject(query) or query[:160],
                    "resolved_query": query[:1000], "search_query": query[:300]}
                   if explicit_topic else {}),
            })
        refreshed = {**state, "resource_plan": plan, "route": plan.route}
        acquirer = ContextAcquirer(self.runtime)
        if plan.use_stream:
            acquired = acquirer.full(refreshed) if plan.use_rag else acquirer.stream(refreshed)
        elif plan.use_tools:
            acquired = acquirer.tools(refreshed)
        else:
            acquired = acquirer.rag(refreshed) if plan.use_rag else acquirer.cag(refreshed)
        refreshed.update(acquired)
        calls = refreshed["model_calls"] + 1
        try:
            draft = provider.generate(
                state["request"],
                refreshed["route"],
                refreshed["evidence"],
                state["alerts"],
                state["statistics"],
                [f"User revision request: {state['review_feedback']}"],
                plan=refreshed["resource_plan"],
            )
        except ProviderError as exc:
            return {
                **acquired,
                "evidence": deduplicate_evidence(state["evidence"] + acquired["evidence"]),
                **self._elapsed(state),
                "revision_error": str(exc),
                "model_calls": calls,
                "trace": refreshed["trace"] + ["revision:failed"],
            }
        return {
            **acquired,
            **self._elapsed(state),
            "draft": draft,
            "validation_errors": [],
            "generation_attempts": state["generation_attempts"] + 1,
            "model_calls": calls,
            "provider_fallback": False,
            "trace": refreshed["trace"] + [f"revision:attempt={state['revision_count']}"],
        }

    @staticmethod
    def _elapsed(state: GraphState) -> dict:
        now = time.perf_counter()
        return {
            "active_ms": state.get("active_ms", 0.0)
            + (now - state["started_at"]) * 1000,
            "started_at": now,
        }
