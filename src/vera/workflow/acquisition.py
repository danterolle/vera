from vera.domain.enums import EvidenceStatus
from vera.domain.evidence import Evidence, make_evidence
from vera.domain.state import GraphState
from vera.stream.evidence import summarize_stream
from vera.workflow.evidence import deduplicate_evidence
from vera.workflow.runtime import Runtime


class ContextAcquirer:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def cag(self, state: GraphState) -> dict:
        query = state["request"].query
        evidence = self.runtime.knowledge.search(query) + state["memory"]
        return self._result(state, evidence, "cag")

    def rag(self, state: GraphState) -> dict:
        query = state["request"].query
        evidence = (
            self.runtime.knowledge.search(query)
            + self.runtime.corpus.search(query, self.runtime.settings.retrieval_k)
            + state["memory"]
        )
        return self._result(state, evidence, "cag+rag")

    def tools(self, state: GraphState) -> dict:
        query = state["request"].query
        local = (
            self.runtime.knowledge.search(query)
            + self.runtime.corpus.search(query, self.runtime.settings.retrieval_k)
            + state["memory"]
        )
        if self.runtime.settings.react_enabled:
            return self._result(state, local, "cag+rag")
        lookup = self.runtime.sources.lookup(state["resource_plan"].cve_ids)
        return self._result(
            state,
            local + lookup.evidence,
            "cag+rag+tools",
            tool_calls=lookup.tool_calls,
            warnings=lookup.warnings,
        )

    def stream(self, state: GraphState) -> dict:
        query = f"{state['request'].query} incident response network traffic"
        evidence = (
            self.runtime.knowledge.search(query)
            + [self._stream_evidence(state)]
            + state["memory"]
        )
        return self._result(state, evidence, "stream")

    def full(self, state: GraphState) -> dict:
        technique_ids = state["resource_plan"].technique_ids
        cve_ids = state["resource_plan"].cve_ids
        expanded = f"{state['request'].query} {' '.join(technique_ids + cve_ids)}"
        lookup = (
            None if self.runtime.settings.react_enabled else self.runtime.sources.lookup(cve_ids)
        )
        evidence = (
            self.runtime.knowledge.search(expanded)
            + self.runtime.corpus.search(expanded, self.runtime.settings.retrieval_k)
            + [self._stream_evidence(state)]
            + (lookup.evidence if lookup else [])
            + state["memory"]
        )
        return self._result(
            state,
            evidence,
            "full",
            tool_calls=lookup.tool_calls if lookup else 0,
            warnings=lookup.warnings if lookup else [],
        )

    @staticmethod
    def _stream_evidence(state: GraphState) -> Evidence:
        request = state["request"]
        simulated = request.simulated or any(event.simulated for event in request.events)
        content, metadata = summarize_stream(state["statistics"], state["alerts"])
        return make_evidence(
            source="stream",
            title="Normalized event-stream analysis",
            content=content,
            status=EvidenceStatus.SIMULATED if simulated else EvidenceStatus.AVAILABLE,
            metadata=metadata,
        )

    @staticmethod
    def _result(
        state: GraphState,
        evidence: list[Evidence],
        label: str,
        *,
        tool_calls: int = 0,
        warnings: list[str] | None = None,
    ) -> dict:
        unique = deduplicate_evidence(evidence)
        return {
            "evidence": unique,
            "tool_calls": state["tool_calls"] + tool_calls,
            "warnings": state["warnings"] + (warnings or []),
            "trace": state["trace"] + [f"context:{label}:evidence={len(unique)}"],
        }
