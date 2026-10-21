import time

from vera.domain.state import GraphState
from vera.reasoning.reflection import reflect
from vera.reasoning.validation import validate_and_repair
from vera.stream.detectors import detect_events
from vera.stream.incident import build_incident
from vera.stream.policy import DetectionPolicy
from vera.stream.statistics import calculate_statistics
from vera.workflow.finalization import finalize_result
from vera.workflow.generation import generate_draft
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
            "started_at": time.perf_counter(),
            "active_ms": 0.0,
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
            and not state.get("revision_count", 0)
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
        return finalize_result(self.runtime, state)
