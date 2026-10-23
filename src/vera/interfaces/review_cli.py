import json
import sys
from typing import Annotated
from uuid import uuid4

import typer

from vera.config import Settings
from vera.domain.reports import AnalysisResult
from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus
from vera.errors import ReviewUnavailable, VeraError
from vera.interfaces.review_render import echo_review, prompt_decision
from vera.workflow.orchestrator import VeraOrchestrator


def register_commands(app: typer.Typer) -> None:
    app.command("reviews")(list_reviews)
    app.command("review")(review)


def prompt_review(engine: VeraOrchestrator, record: ReviewRecord) -> None:
    echo_review(record)
    apply_decision(engine, record, prompt_decision(record), json_output=False)


def new_decision(
    record: ReviewRecord, action: str, feedback: str | None = None
) -> ReviewDecision:
    if record.status == ReviewStatus.ERROR:
        retry = record.retry_decision
        if retry is None:
            raise ReviewUnavailable("The interrupted decision cannot be retried")
        if retry.action != action or (
            feedback is not None and feedback.strip() != retry.feedback
        ):
            raise ReviewUnavailable("Use --retry to repeat the interrupted decision")
        return retry
    if record.status != ReviewStatus.PENDING:
        raise ReviewUnavailable(f"Review is {record.status.value}; no decision is possible")
    return ReviewDecision(
        action=action,
        version=record.version,
        decision_id=uuid4(),
        feedback=feedback,
    )


def apply_decision(
    engine: VeraOrchestrator,
    record: ReviewRecord,
    decision: ReviewDecision,
    *,
    json_output: bool,
) -> None:
    try:
        outcome = engine.decide_review(record.run_id, decision)
    except (VeraError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if isinstance(outcome, AnalysisResult):
        typer.echo(outcome.model_dump_json(indent=2) if json_output else outcome.answer)
        raise typer.Exit(code=0)
    if json_output:
        typer.echo(outcome.model_dump_json(indent=2))
    elif outcome.status == ReviewStatus.REJECTED:
        typer.echo(f"Review {outcome.run_id} rejected; no report was published.")
        raise typer.Exit(code=0)
    else:
        echo_review(outcome)
        typer.echo(f"Revision recorded. Review {outcome.run_id} is still pending.")
    raise typer.Exit(code=2)


def list_reviews(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the complete JSON review list."),
    ] = False,
) -> None:
    try:
        with VeraOrchestrator(Settings()) as engine:
            records = engine.list_reviews()
    except (VeraError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(
            json.dumps([record.model_dump(mode="json") for record in records], indent=2)
        )
        return
    if not records:
        typer.echo("No open reviews.")
        return
    typer.echo(f"{len(records)} open review(s):")
    for record in records:
        typer.echo(
            f"- {record.run_id} [{record.status.value}] {record.route.value} "
            f"v{record.version}: {record.query}"
        )
        for reason in record.reasons:
            typer.echo(f"  {reason}")


def review(
    run_id: Annotated[str, typer.Argument(help="Pending review run ID.")],
    approve: Annotated[
        bool,
        typer.Option("--approve", help="Approve the draft and publish the report."),
    ] = False,
    reject: Annotated[
        str | None,
        typer.Option("--reject", help="Reject the draft with required feedback."),
    ] = None,
    revise: Annotated[
        str | None,
        typer.Option("--revise", help="Request a revision with required feedback."),
    ] = None,
    retry: Annotated[
        bool,
        typer.Option("--retry", help="Retry the interrupted decision for this review."),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option("--interactive", help="Prompt for the decision on standard input."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the complete JSON review or result."),
    ] = False,
) -> None:
    actions = sum((approve, reject is not None, revise is not None, retry))
    if actions > 1:
        raise typer.BadParameter("Use only one of --approve, --reject, --revise, or --retry")
    if interactive and actions:
        raise typer.BadParameter("--interactive cannot be combined with an explicit action")
    if json_output and interactive:
        raise typer.BadParameter("--json cannot be combined with --interactive")
    if reject is not None and not reject.strip():
        raise typer.BadParameter("--reject requires feedback")
    if revise is not None and not revise.strip():
        raise typer.BadParameter("--revise requires feedback")
    with VeraOrchestrator(Settings()) as engine:
        try:
            record = engine.get_review(run_id)
        except (VeraError, ValueError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if record is None:
            typer.echo(f"Error: review {run_id} was not found", err=True)
            raise typer.Exit(code=1)
        action = None
        feedback = None
        if approve:
            action = "approve"
        elif reject is not None:
            action = "reject"
            feedback = reject.strip()
        elif revise is not None:
            action = "revise"
            feedback = revise.strip()
        if retry:
            if record.status != ReviewStatus.ERROR or record.retry_decision is None:
                typer.echo("Error: there is no interrupted decision to retry", err=True)
                raise typer.Exit(code=1)
            decision = record.retry_decision
        elif action is not None:
            try:
                decision = new_decision(record, action, feedback)
            except VeraError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        else:
            if json_output:
                typer.echo(record.model_dump_json(indent=2))
                return
            echo_review(record)
            if interactive or sys.stdin.isatty():
                apply_decision(engine, record, prompt_decision(record), json_output=False)
            if record.status == ReviewStatus.ERROR:
                typer.echo(f"Review left in error. Run: vera review {run_id} --retry")
                raise typer.Exit(code=2)
            if record.status == ReviewStatus.PENDING:
                typer.echo(f"Review left pending. Run: vera review {run_id} --interactive")
                raise typer.Exit(code=2)
            typer.echo(f"Review {run_id} is {record.status.value}; no action is possible.")
            return
        apply_decision(engine, record, decision, json_output=json_output)
