from uuid import uuid4

import typer

from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus


def echo_review(record: ReviewRecord) -> None:
    typer.echo(f"Review {record.run_id}")
    typer.echo(f"Status: {record.status.value} (version {record.version})")
    typer.echo(f"Query: {record.query}")
    typer.echo(f"Route: {record.route.value}")
    if record.reasons:
        typer.echo("Reasons:")
        for reason in record.reasons:
            typer.echo(f"- {reason}")
    typer.echo("Unpublished draft:")
    typer.echo(record.draft.summary)
    if record.draft.claims:
        typer.echo("Claims:")
        for claim in record.draft.claims:
            typer.echo(f"- [{claim.status.value}] {claim.text}")
            for citation in claim.citations:
                typer.echo(f"  quote: {citation.supporting_quote}")
    if record.evidence:
        typer.echo("Evidence:")
        for item in record.evidence:
            typer.echo(f"- {item.id} [{item.source.value}/{item.status.value}] {item.title}")
    if record.incident is not None:
        typer.echo(f"Incident: {record.incident.severity.value} {record.incident.title}")
        for alert in record.incident.alerts:
            typer.echo(f"- {alert.rule_id} {alert.title} (confidence {alert.confidence:.0%})")
    if record.warnings:
        typer.echo("Warnings:")
        for warning in record.warnings:
            typer.echo(f"- {warning}")
    if record.feedback_history:
        typer.echo("Feedback history:")
        for feedback in record.feedback_history:
            typer.echo(f"- {feedback}")
    if record.error:
        typer.echo(f"Error: {record.error}")


def prompt_feedback(label: str) -> str:
    while True:
        feedback = typer.prompt(f"Feedback for {label}").strip()
        if not feedback:
            typer.echo("Feedback is required.", err=True)
            continue
        if len(feedback) > 4000:
            typer.echo("Feedback must be at most 4000 characters.", err=True)
            continue
        return feedback


def prompt_decision(record: ReviewRecord) -> ReviewDecision:
    if record.status == ReviewStatus.ERROR:
        if record.retry_decision is None:
            typer.echo("The review has an error without a retryable decision.", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"An interrupted {record.retry_decision.action} decision can be retried.")
        if typer.confirm("Retry it now?", default=True):
            return record.retry_decision
        typer.echo(f"Review left unchanged. Run: vera review {record.run_id} --retry")
        raise typer.Exit(code=2)
    if record.status != ReviewStatus.PENDING:
        typer.echo(f"Review {record.run_id} is already {record.status.value}.")
        raise typer.Exit(code=0)
    choices = "a=approve, r=reject, v=revise, q=quit"
    if not record.can_revise:
        choices = "a=approve, r=reject, q=quit"
    while True:
        choice = typer.prompt(f"Decision ({choices})", default="q").strip().lower()
        if choice in {"q", "quit"}:
            typer.echo(f"Review left pending. Run: vera review {record.run_id}")
            raise typer.Exit(code=2)
        if choice in {"a", "approve"}:
            action = "approve"
            feedback = None
        elif choice in {"r", "reject"}:
            action = "reject"
            feedback = prompt_feedback("rejection")
        elif choice in {"v", "revise"}:
            if not record.can_revise:
                typer.echo("Revision requires an external model provider.", err=True)
                continue
            action = "revise"
            feedback = prompt_feedback("revision")
        else:
            typer.echo(f"Invalid choice: {choice}", err=True)
            continue
        return ReviewDecision(
            action=action,
            version=record.version,
            decision_id=uuid4(),
            feedback=feedback,
        )
