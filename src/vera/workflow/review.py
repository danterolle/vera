import time

from langgraph.types import interrupt

from vera.domain.review import ReviewDecision
from vera.domain.state import GraphState
from vera.errors import ProviderError
from vera.reasoning.review import review_reasons
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
        calls = state["model_calls"] + 1
        try:
            draft = provider.generate(
                state["request"],
                state["route"],
                state["evidence"],
                state["alerts"],
                state["statistics"],
                [state["review_feedback"]],
            )
        except ProviderError as exc:
            return {
                **self._elapsed(state),
                "revision_error": str(exc),
                "model_calls": calls,
                "trace": state["trace"] + ["revision:failed"],
            }
        return {
            **self._elapsed(state),
            "draft": draft,
            "validation_errors": [],
            "generation_attempts": state["generation_attempts"] + 1,
            "model_calls": calls,
            "provider_fallback": False,
            "trace": state["trace"] + [f"revision:attempt={state['revision_count']}"],
        }

    @staticmethod
    def _elapsed(state: GraphState) -> dict:
        now = time.perf_counter()
        return {
            "active_ms": state.get("active_ms", 0.0)
            + (now - state["started_at"]) * 1000,
            "started_at": now,
        }
