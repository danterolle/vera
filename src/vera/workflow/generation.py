from vera.domain.enums import ClaimStatus, EvidenceStatus, SourceType
from vera.domain.evidence import Citation, Claim, Evidence
from vera.domain.reports import GeneratedAnswer
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
                plan=state["resource_plan"],
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
            plan=state["resource_plan"],
        )
    repaired = _ensure_claim(draft, state["evidence"])
    if repaired.claims and not draft.claims:
        warnings.append(
            "The model returned no claims; a claim was derived from the highest-ranked evidence."
        )
    return {
        "draft": repaired,
        "generation_attempts": attempts,
        "model_calls": calls,
        "provider_fallback": fallback,
        "warnings": warnings,
        "trace": state["trace"] + [f"generation:attempt={attempts}:provider={provider.name}"],
    }


def best_evidence_claim(evidence: list[Evidence]) -> Claim | None:
    selected = next(
        (
            item for item in evidence
            if item.status == EvidenceStatus.AVAILABLE
            and item.source not in {SourceType.MEMORY, SourceType.STREAM}
            and not item.metadata.get("fallback", False)
        ),
        None,
    )
    if selected is None:
        return None
    quote = selected.content[:4000]
    return Claim(
        text=quote,
        status=ClaimStatus.SUPPORTED_FACT,
        evidence_ids=[selected.id],
        citations=[Citation(evidence_id=selected.id, supporting_quote=quote)],
    )


def _ensure_claim(draft: GeneratedAnswer, evidence: list[Evidence]) -> GeneratedAnswer:
    if draft.claims or draft.out_of_scope:
        return draft
    claim = best_evidence_claim(evidence)
    if claim is None:
        return draft
    return draft.model_copy(update={"claims": [claim]})


def _deterministic(state: GraphState):
    return DeterministicProvider().generate(
        state["request"],
        state["route"],
        state["evidence"],
        state["alerts"],
        state["statistics"],
        state["validation_errors"],
        plan=state["resource_plan"],
    )
