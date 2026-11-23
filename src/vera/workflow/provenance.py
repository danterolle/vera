from vera.domain.state import DraftSource, GraphState
from vera.reasoning.validation import VALIDATION_CONTRACT
from vera.workflow.runtime import Runtime

STALE_DRAFT = (
    "This draft was not validated under the current contract. Revise it or run a new analysis."
)


def draft_source(runtime: Runtime, *, fallback: bool = False) -> DraftSource:
    provider = runtime.provider
    external = provider.external and not fallback
    return {
        "provider": "deterministic" if fallback else provider.name,
        "model": runtime.settings.llm_model if external else None,
        "external": external,
    }


def has_current_validation(state: GraphState) -> bool:
    return state.get("validation_contract") == VALIDATION_CONTRACT and bool(
        state.get("draft_source")
    )


def draft_metadata(state: GraphState) -> dict:
    source = state.get("draft_source")
    return {
        "provider": source["provider"] if source else None,
        "model": source["model"] if source else None,
        "provider_fallback": state["provider_fallback"],
        "validation_contract": state.get("validation_contract"),
        "summary_requires_review": bool(state.get("summary_errors")),
    }
