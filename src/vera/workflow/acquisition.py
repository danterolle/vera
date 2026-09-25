import json

from vera.domain.enums import EvidenceStatus
from vera.domain.evidence import Evidence, make_evidence
from vera.domain.state import GraphState
from vera.retrieval.cve import extract_cve_ids
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
        lookup = self.runtime.sources.lookup(extract_cve_ids(query))
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
        technique_ids = [
            alert.technique_id for alert in state["alerts"] if alert.technique_id is not None
        ]
        alert_cves = [cve for alert in state["alerts"] for cve in alert.cve_ids]
        query_cves = extract_cve_ids(state["request"].query)
        cve_ids = sorted(set(alert_cves + query_cves))
        expanded = f"{state['request'].query} {' '.join(technique_ids + cve_ids)}"
        lookup = self.runtime.sources.lookup(cve_ids)
        evidence = (
            self.runtime.knowledge.search(expanded)
            + self.runtime.corpus.search(expanded, self.runtime.settings.retrieval_k)
            + [self._stream_evidence(state)]
            + lookup.evidence
            + state["memory"]
        )
        return self._result(
            state,
            evidence,
            "full",
            tool_calls=lookup.tool_calls,
            warnings=lookup.warnings,
        )

    @staticmethod
    def _stream_evidence(state: GraphState) -> Evidence:
        request = state["request"]
        simulated = request.simulated or any(event.simulated for event in request.events)
        payload = {
            "statistics": state["statistics"].model_dump(mode="json"),
            "alerts": [alert.model_dump(mode="json") for alert in state["alerts"]],
        }
        return make_evidence(
            source="stream",
            title="Normalized event-stream analysis",
            content=json.dumps(payload, sort_keys=True),
            status=EvidenceStatus.SIMULATED if simulated else EvidenceStatus.AVAILABLE,
            metadata={"event_count": len(request.events)},
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
        unique = list({item.id: item for item in evidence}.values())
        return {
            "evidence": unique,
            "tool_calls": state["tool_calls"] + tool_calls,
            "warnings": state["warnings"] + (warnings or []),
            "trace": state["trace"] + [f"context:{label}:evidence={len(unique)}"],
        }
