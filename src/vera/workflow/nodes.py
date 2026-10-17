import time
from uuid import uuid4

from vera.domain.enums import ClaimStatus
from vera.domain.reports import AnalysisResult, RunMetrics
from vera.domain.state import GraphState
from vera.providers.rendering import render_answer
from vera.reasoning.reflection import reflect
from vera.reasoning.validation import validate_and_repair
from vera.stream.detectors import detect_events
from vera.stream.incident import build_incident
from vera.stream.policy import DetectionPolicy
from vera.stream.statistics import calculate_statistics
from vera.workflow.generation import generate_draft
from vera.workflow.knowledge_graph import graph_metadata, persist_result
from vera.workflow.runtime import Runtime


class WorkflowNodes:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def initialize(self, state: GraphState) -> dict:
        request = state["request"]
        settings = self.runtime.settings
        alerts = detect_events(
            request.events,
            DetectionPolicy(
                port_scan_threshold=settings.port_scan_threshold,
                port_scan_window_seconds=settings.port_scan_window_seconds,
                auth_failure_threshold=settings.auth_failure_threshold,
                auth_failure_window_seconds=settings.auth_failure_window_seconds,
                syn_burst_threshold=settings.syn_burst_threshold,
                syn_burst_window_seconds=settings.syn_burst_window_seconds,
            ),
        )
        statistics = calculate_statistics(request.events)
        memory = self.runtime.memory.recall(
            request.query,
            self.runtime.settings.memory_k,
            request.session_id,
        )
        return {
            "run_id": str(uuid4()),
            "started_at": time.perf_counter(),
            "alerts": alerts,
            "statistics": statistics,
            "incident": build_incident(alerts, statistics),
            "memory": memory,
            "evidence": [],
            "generation_attempts": 0,
            "validation_errors": [],
            "retry_generation": False,
            "provider_fallback": False,
            "model_calls": 0,
            "tool_calls": 0,
            "react_steps": 0,
            "react_searches": [],
            "react_lookups": [],
            "react_observations": [],
            "trace": [
                f"initialized:events={len(request.events)}:alerts={len(alerts)}",
                f"memory:recalled={len(memory)}",
            ],
            "warnings": [],
        }

    def route(self, state: GraphState) -> dict:
        decision = self.runtime.router.select(
            state["request"].query,
            bool(state["request"].events),
            state["alerts"],
        )
        return {
            "route": decision.route,
            "route_reason": decision.reason,
            "resource_plan": decision.plan,
            "model_calls": state["model_calls"] + decision.model_calls,
            "warnings": state["warnings"] + decision.warnings,
            "trace": state["trace"] + [f"route:{decision.route.value}:{decision.reason}"],
        }

    def generate(self, state: GraphState) -> dict:
        return generate_draft(self.runtime, state)

    def validate(self, state: GraphState) -> dict:
        initial = validate_and_repair(
            state["draft"],
            state["evidence"],
            repair=False,
            minimum_coverage=self.runtime.settings.grounding_min_coverage,
        )
        can_retry = (
            bool(initial.errors)
            and self.runtime.provider.external
            and not state["provider_fallback"]
            and state["generation_attempts"] < self.runtime.settings.generation_attempt_limit
            and state["model_calls"] < self.runtime.settings.model_call_limit
        )
        if can_retry:
            return {
                "validation_errors": initial.errors,
                "retry_generation": True,
                "trace": state["trace"] + [f"validation:retry={len(initial.errors)}"],
            }
        final = validate_and_repair(
            initial.draft,
            state["evidence"],
            repair=True,
            minimum_coverage=self.runtime.settings.grounding_min_coverage,
        )
        return {
            "draft": final.draft,
            "validation_errors": initial.errors,
            "retry_generation": False,
            "trace": state["trace"] + [f"validation:errors={len(initial.errors)}"],
        }

    def reflection(self, state: GraphState) -> dict:
        report = reflect(
            state["draft"].claims,
            state["evidence"],
            state["validation_errors"],
        )
        return {
            "reflection": report,
            "trace": state["trace"] + [f"reflection:score={report.completeness_score:.2f}"],
        }

    def finalize(self, state: GraphState) -> dict:
        claims = state["draft"].claims
        factual = [
            claim
            for claim in claims
            if claim.status == ClaimStatus.SUPPORTED_FACT
        ]
        assessable = [
            claim
            for claim in claims
            if claim.status in {ClaimStatus.SUPPORTED_FACT, ClaimStatus.SYSTEM_INFERENCE}
        ]
        hidden_failures = max(
            0,
            state["reflection"].grounding_failures
            - sum(claim.status == ClaimStatus.SYSTEM_INFERENCE for claim in claims),
        )
        grounded = sum(bool(claim.citations) for claim in factual)
        denominator = len(assessable) + hidden_failures
        coverage = grounded / denominator if denominator else 1.0
        trace = state["trace"] + ["persistence:sqlite"]
        metadata = {
            "provider": self.runtime.provider.name,
            "model": self.runtime.settings.llm_model if self.runtime.provider.external else None,
            "provider_fallback": state["provider_fallback"],
            "out_of_scope": state["draft"].out_of_scope,
            "embedding_backend": self.runtime.embedder.name,
            "route_reason": state["route_reason"],
            "resource_plan": state["resource_plan"].model_dump(mode="json"),
            "knowledge_graph": graph_metadata(state),
        }
        if self.runtime.settings.react_enabled:
            metadata["react_enabled"] = True
            metadata["model_call_limit"] = self.runtime.settings.model_call_limit
            metadata["react_steps"] = state["react_steps"]
            metadata["generation_attempts"] = state["generation_attempts"]
            metadata["react_observations"] = [
                item.model_dump(mode="json") for item in state["react_observations"]
            ]
        result = AnalysisResult(
            run_id=state["run_id"],
            route=state["route"],
            answer=render_answer(
                state["draft"].summary,
                claims,
                state["evidence"],
                state["incident"],
            ),
            claims=claims,
            evidence=state["evidence"],
            incident=state["incident"],
            reflection=state["reflection"],
            metrics=RunMetrics(
                latency_ms=(time.perf_counter() - state["started_at"]) * 1000,
                model_calls=state["model_calls"],
                tool_calls=state["tool_calls"],
                retrieved_documents=len(state["evidence"]),
                source_coverage=round(coverage, 3),
            ),
            trace=trace,
            warnings=state["warnings"],
            metadata=metadata,
        )
        persist_result(self.runtime, state, result)
        return {"result": result, "trace": trace}
