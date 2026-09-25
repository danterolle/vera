import time
from uuid import uuid4

from vera.domain.enums import ClaimStatus
from vera.domain.reports import AnalysisResult, RunMetrics
from vera.domain.state import GraphState
from vera.errors import ProviderError
from vera.providers.deterministic import DeterministicProvider
from vera.providers.rendering import render_answer
from vera.reasoning.reflection import reflect
from vera.reasoning.validation import validate_and_repair
from vera.stream.detectors import detect_events
from vera.stream.incident import build_incident
from vera.stream.statistics import calculate_statistics
from vera.workflow.runtime import Runtime


class WorkflowNodes:
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def initialize(self, state: GraphState) -> dict:
        request = state["request"]
        alerts = detect_events(request.events)
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
            bool(state["alerts"]),
        )
        return {
            "route": decision.route,
            "route_reason": decision.reason,
            "model_calls": state["model_calls"] + decision.model_calls,
            "warnings": state["warnings"] + decision.warnings,
            "trace": state["trace"] + [f"route:{decision.route.value}:{decision.reason}"],
        }

    def generate(self, state: GraphState) -> dict:
        attempts = state["generation_attempts"] + 1
        calls = state["model_calls"]
        warnings = list(state["warnings"])
        fallback = state["provider_fallback"]
        provider = self.runtime.provider
        budget_exhausted = (
            provider.external and calls >= self.runtime.settings.max_model_calls
        )
        if budget_exhausted:
            warnings.append("The model-call limit was reached; deterministic output used.")
            fallback = True
            draft = DeterministicProvider().generate(
                state["request"],
                state["route"],
                state["evidence"],
                state["alerts"],
                state["statistics"],
                state["validation_errors"],
            )
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
                draft = DeterministicProvider().generate(
                    state["request"],
                    state["route"],
                    state["evidence"],
                    state["alerts"],
                    state["statistics"],
                    state["validation_errors"],
                )
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

    def validate(self, state: GraphState) -> dict:
        initial = validate_and_repair(state["draft"], state["evidence"], repair=False)
        can_retry = (
            bool(initial.errors)
            and self.runtime.provider.external
            and not state["provider_fallback"]
            and state["model_calls"] < self.runtime.settings.max_model_calls
        )
        if can_retry:
            return {
                "validation_errors": initial.errors,
                "retry_generation": True,
                "trace": state["trace"] + [f"validation:retry={len(initial.errors)}"],
            }
        final = validate_and_repair(initial.draft, state["evidence"], repair=True)
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
            if claim.status in {ClaimStatus.SUPPORTED_FACT, ClaimStatus.SYSTEM_INFERENCE}
        ]
        covered = sum(bool(claim.evidence_ids) for claim in factual)
        coverage = covered / len(factual) if factual else 1.0
        trace = state["trace"] + ["persistence:sqlite"]
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
            metadata={
                "provider": self.runtime.provider.name,
                "embedding_backend": self.runtime.embedder.name,
                "route_reason": state["route_reason"],
            },
        )
        self.runtime.memory.save(state["request"], result)
        return {"result": result, "trace": trace}
