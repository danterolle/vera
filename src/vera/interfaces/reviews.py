from fastapi import FastAPI, HTTPException, Response

from vera.domain.reports import AnalysisResult
from vera.domain.review import ReviewDecision, ReviewRecord
from vera.errors import ReviewConflict, ReviewUnavailable
from vera.workflow.orchestrator import VeraOrchestrator


def register_review_routes(application: FastAPI, engine: VeraOrchestrator) -> None:
    @application.get("/v1/reviews", response_model=list[ReviewRecord])
    def list_reviews() -> list[ReviewRecord]:
        try:
            return engine.list_reviews()
        except ReviewUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get("/v1/reviews/{run_id}", response_model=ReviewRecord)
    def get_review(run_id: str) -> ReviewRecord:
        try:
            record = engine.get_review(run_id)
        except ReviewUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if record is None:
            raise HTTPException(status_code=404, detail="Review not found")
        return record

    @application.post(
        "/v1/reviews/{run_id}/decisions",
        response_model=AnalysisResult | ReviewRecord,
    )
    def decide(
        run_id: str, decision: ReviewDecision, response: Response
    ) -> AnalysisResult | ReviewRecord:
        try:
            outcome = engine.decide_review(run_id, decision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Review not found") from exc
        except ReviewConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ReviewUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if isinstance(outcome, ReviewRecord) and outcome.status == "pending":
            response.status_code = 202
        return outcome
