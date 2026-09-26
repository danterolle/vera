from typing import Literal

from pydantic import ValidationError

from vera.domain.actions import ReActAction, ReActObservation
from vera.domain.state import GraphState
from vera.errors import ConfigurationError, ProviderError
from vera.providers.react import ReActProvider
from vera.workflow.evidence import deduplicate_evidence
from vera.workflow.runtime import Runtime


class ReActEvidenceNodes:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def decide(self, state: GraphState) -> dict:
        settings = self.runtime.settings
        calls = state["model_calls"]
        steps = state["react_steps"]
        warnings = list(state["warnings"])
        if steps >= settings.max_react_steps:
            warnings.append("The ReAct step limit was reached; generating an answer.")
            action = ReActAction(action="finish")
        elif calls >= settings.model_call_limit - settings.generation_attempt_limit:
            warnings.append(
                "ReAct stopped to reserve model calls for the answer and one correction."
            )
            action = ReActAction(action="finish")
        else:
            provider = self.runtime.provider
            if not isinstance(provider, ReActProvider):
                raise ConfigurationError(
                    "ReAct requires an external provider with action decisions"
                )
            calls += 1
            steps += 1
            try:
                action = ReActAction.model_validate(
                    provider.decide_action(
                        state["request"].query,
                        state["evidence"],
                        state["resource_plan"].cve_ids,
                        state["react_observations"],
                    )
                )
            except (ProviderError, ValidationError) as exc:
                warnings.append(f"ReAct decision failed; generating an answer: {exc}")
                action = ReActAction(action="finish")
        return {
            "react_action": action,
            "react_steps": steps,
            "model_calls": calls,
            "warnings": warnings,
            "trace": state["trace"] + [f"react:decision={action.action}"],
        }

    def execute(self, state: GraphState) -> dict:
        action = state["react_action"]
        evidence = state["evidence"]
        warnings = list(state["warnings"])
        calls = state["tool_calls"]
        searches = list(state["react_searches"])
        lookups = list(state["react_lookups"])
        outcome: Literal["completed", "skipped", "rejected"] = "completed"
        if action.action == "search_corpus":
            query = action.query
            if query is None:
                raise ProviderError("ReAct corpus search is missing a query")
            if query in searches:
                outcome = "skipped"
                warnings.append("ReAct skipped a repeated corpus search.")
            else:
                searches.append(query)
                evidence = deduplicate_evidence(
                    evidence + self.runtime.corpus.search(query, self.runtime.settings.retrieval_k)
                )
        elif action.action == "lookup_cve":
            cve_id = action.cve_id
            if cve_id is None:
                raise ProviderError("ReAct CVE lookup is missing an identifier")
            if cve_id not in state["resource_plan"].cve_ids:
                outcome = "rejected"
                warnings.append("ReAct rejected a CVE identifier outside the request.")
            elif cve_id in lookups:
                outcome = "skipped"
                warnings.append("ReAct skipped a repeated CVE lookup.")
            else:
                lookups.append(cve_id)
                lookup = self.runtime.sources.lookup(
                    [cve_id], limit=max(0, self.runtime.settings.max_tool_calls - calls)
                )
                evidence = deduplicate_evidence(evidence + lookup.evidence)
                calls += lookup.tool_calls
                warnings.extend(lookup.warnings)
        else:
            raise ProviderError("ReAct cannot execute a finish action")
        previous_ids = {item.id for item in state["evidence"]}
        observation = ReActObservation(
            action=action,
            outcome=outcome,
            evidence_ids=[item.id for item in evidence if item.id not in previous_ids],
        )
        return {
            "evidence": evidence,
            "react_searches": searches,
            "react_lookups": lookups,
            "react_observations": state["react_observations"] + [observation],
            "tool_calls": calls,
            "warnings": warnings,
            "trace": state["trace"] + [f"react:execute={action.action}:evidence={len(evidence)}"],
        }
