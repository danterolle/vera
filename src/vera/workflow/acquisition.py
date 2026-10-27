from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence
from vera.domain.state import GraphState
from vera.knowledge_graph.retrieval import search_graph
from vera.knowledge_graph.selection import combine_evidence
from vera.retrieval.subjects import concept_subject, names_subject
from vera.workflow.evidence import context_query, deduplicate_evidence, stream_evidence
from vera.workflow.runtime import Runtime
from vera.workflow.source_assessment import assess_online_sources


class ContextAcquirer:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def cag(self, state: GraphState) -> dict:
        if state["resource_plan"].intent != "cybersecurity":
            return self._result(state, [], "conversation")
        query = context_query(state)
        evidence = self.runtime.knowledge.search(query) + state["memory"]
        subject = state["resource_plan"].subject or concept_subject(query)
        if self._covered(evidence, subject):
            return self._result(state, evidence, "cag")
        # Curated knowledge has no record about the subject: escalate to local
        # retrieval and bounded online research instead of answering from memory.
        return self.rag(state)

    def rag(self, state: GraphState) -> dict:
        query = context_query(state)
        evidence = (
            self.runtime.knowledge.search(query)
            + self.runtime.corpus.search(query, self.runtime.settings.retrieval_k)
            + state["memory"]
        )
        return self._result(state, evidence, "cag+rag", searched_query=query)

    def tools(self, state: GraphState) -> dict:
        query = context_query(state)
        local = (
            self.runtime.knowledge.search(query)
            + self.runtime.corpus.search(query, self.runtime.settings.retrieval_k)
            + state["memory"]
        )
        if self.runtime.settings.react_enabled:
            return self._result(state, local, "cag+rag", searched_query=query)
        lookup = self.runtime.sources.lookup(
            state["resource_plan"].cve_ids,
            limit=max(0, self.runtime.settings.max_tool_calls - state["tool_calls"]),
        )
        return self._result(
            state,
            local + lookup.evidence,
            "cag+rag+tools",
            tool_calls=lookup.tool_calls,
            warnings=lookup.warnings,
            searched_query=query,
        )

    def stream(self, state: GraphState) -> dict:
        query = f"{state['request'].query} incident response network traffic"
        evidence = (
            self.runtime.knowledge.search(query)
            + [stream_evidence(state)]
            + state["memory"]
        )
        return self._result(state, evidence, "stream")

    def full(self, state: GraphState) -> dict:
        technique_ids = state["resource_plan"].technique_ids
        cve_ids = state["resource_plan"].cve_ids
        expanded = f"{state['request'].query} {' '.join(technique_ids + cve_ids)}"
        lookup = (
            None if self.runtime.settings.react_enabled else self.runtime.sources.lookup(
                cve_ids,
                limit=max(0, self.runtime.settings.max_tool_calls - state["tool_calls"]),
            )
        )
        evidence = (
            self.runtime.knowledge.search(expanded)
            + self.runtime.corpus.search(expanded, self.runtime.settings.retrieval_k)
            + [stream_evidence(state)]
            + (lookup.evidence if lookup else [])
            + state["memory"]
        )
        return self._result(
            state,
            evidence,
            "full",
            tool_calls=lookup.tool_calls if lookup else 0,
            warnings=lookup.warnings if lookup else [],
            searched_query=expanded,
        )

    @staticmethod
    def _covered(evidence: list[Evidence], subject: str | None) -> bool:
        return any(
            item.status == EvidenceStatus.AVAILABLE
            and item.source not in {SourceType.MEMORY, SourceType.STREAM}
            and not item.metadata.get("fallback", False)
            and (subject is None or names_subject(item, subject))
            for item in evidence
        )

    def _result(
        self,
        state: GraphState,
        evidence: list[Evidence],
        label: str,
        *,
        tool_calls: int = 0,
        warnings: list[str] | None = None,
        searched_query: str | None = None,
    ) -> dict:
        graph = None
        if self.runtime.knowledge_graph and searched_query is not None:
            graph = search_graph(self.runtime.knowledge_graph, searched_query)
            evidence = combine_evidence(graph.evidence, evidence)
            if graph.error:
                warnings = [*(warnings or []), graph.error]
        plan = state["resource_plan"]
        subject = plan.subject or concept_subject(searched_query or "")
        definition = bool(concept_subject(state["request"].query)) and bool(subject)
        definition = definition and not state["request"].events
        covered = self._covered(evidence, subject)
        web_query = plan.web_query
        if (plan.intent == "cybersecurity" and searched_query is not None
                and not state["request"].events and not covered and web_query is None):
            web_query = plan.search_query or subject or searched_query
        research_trace = []
        model_calls = state["model_calls"]
        if web_query is not None:
            lookup = self.runtime.sources.research(
                web_query,
                limit=max(
                    0, self.runtime.settings.max_tool_calls - state["tool_calls"] - tool_calls,
                ),
                topic=subject,
            )
            online, model_calls, assessment_warnings, accepted = assess_online_sources(
                self.runtime, state, plan, lookup.evidence, subject=subject,
            )
            warnings = [*(warnings or []), *assessment_warnings]
            if accepted is not None:
                research_trace.append(f"research:validated_sources={accepted}")
            evidence = online + evidence
            tool_calls += lookup.tool_calls
            warnings = [*(warnings or []), *lookup.warnings]
            reason = "Online research was requested or local topic coverage was missing."
            plan = plan.model_copy(update={
                "use_rag": True, "use_tools": True, "web_query": web_query,
                "reasons": list(dict.fromkeys([*plan.reasons, reason])),
            })
            research_trace.append(f"research:http_requests={lookup.tool_calls}:query={web_query}")
        if definition:
            evidence = [item for item in evidence if (
                names_subject(item, subject)
                or item.status == EvidenceStatus.UNAVAILABLE
                or item.source == SourceType.WEB
                or item.metadata.get("fallback")
            )]
        unique = deduplicate_evidence(evidence)
        graph_metadata = graph.model_dump() if graph else {
            "enabled": self.runtime.knowledge_graph is not None, "attempted": False,
        }
        graph_metadata["retained_evidence_ids"] = [
            item.id for item in unique if item.metadata.get("kg_record_key")
        ]
        trace = [f"context:{label}:evidence={len(unique)}"]
        if graph:
            trace.append(
                f"knowledge_graph:attempted={graph.attempted}:"
                f"available={graph.available}:evidence={len(graph_metadata['retained_evidence_ids'])}"
            )
        return {
            "route": plan.route,
            "resource_plan": plan,
            "route_reason": " ".join(plan.reasons),
            "evidence": unique,
            "knowledge_graph": graph_metadata,
            "tool_calls": state["tool_calls"] + tool_calls,
            "model_calls": model_calls,
            "react_searches": state["react_searches"] + (
                [searched_query] if searched_query is not None else []
            ),
            "warnings": list(dict.fromkeys(state["warnings"] + (warnings or []))),
            "trace": state["trace"] + trace + research_trace,
        }
