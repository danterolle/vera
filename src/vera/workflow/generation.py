from vera.domain.state import GraphState
from vera.errors import ProviderError
from vera.providers.deterministic import DeterministicProvider
from vera.workflow.runtime import Runtime


def generate_draft(runtime: Runtime, state: GraphState) -> dict:
    attempts = state["generation_attempts"] + 1
    calls = state["model_calls"]
    warnings = list(state["warnings"])
    fallback = state["provider_fallback"]
    provider = runtime.provider
    budget_exhausted = provider.external and calls >= runtime.settings.model_call_limit
    if budget_exhausted:
        warnings.append("The model-call limit was reached; deterministic output used.")
        fallback = True
        draft = _deterministic(state)
    elif provider.external:
        calls += 1
        try:
            draft = provider.generate(
                state["request"],
                state["route"],
                state["evidence"],
                state["alerts"],
                state["statistics"],
                state["validation_errors"],
            )
        except ProviderError as exc:
            warnings.append(f"LLM generation failed; deterministic output used: {exc}")
            fallback = True
            draft = _deterministic(state)
    else:
        draft = provider.generate(
            state["request"],
            state["route"],
            state["evidence"],
            state["alerts"],
            state["statistics"],
            state["validation_errors"],
        )
    return {
        "draft": draft,
        "generation_attempts": attempts,
        "model_calls": calls,
        "provider_fallback": fallback,
        "warnings": warnings,
        "trace": state["trace"] + [f"generation:attempt={attempts}:provider={provider.name}"],
    }


def _deterministic(state: GraphState):
    return DeterministicProvider().generate(
        state["request"],
        state["route"],
        state["evidence"],
        state["alerts"],
        state["statistics"],
        state["validation_errors"],
    )
