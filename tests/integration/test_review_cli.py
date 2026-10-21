import json
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from vera.config import Settings
from vera.domain.review import ReviewDecision, ReviewRecord, ReviewStatus
from vera.interfaces.cli import app
from vera.workflow.orchestrator import VeraOrchestrator


@pytest.fixture
def cli_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr("vera.interfaces.cli.Settings", lambda: settings)
    monkeypatch.setattr("vera.interfaces.review_cli.Settings", lambda: settings)
    return settings


def test_cli_lists_and_approves_pending_review(cli_settings: Settings) -> None:
    engine = VeraOrchestrator(cli_settings)
    pending = engine.analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(pending, ReviewRecord)
    runner = CliRunner()

    listed = runner.invoke(app, ["reviews", "--json"])
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)[0]["run_id"] == pending.run_id

    approved = runner.invoke(app, ["review", pending.run_id, "--approve"])
    assert approved.exit_code == 0
    assert approved.stdout.strip()
    restored = VeraOrchestrator(cli_settings)
    assert restored.get_run(pending.run_id) is not None
    assert restored.list_reviews() == []


def test_cli_rejects_with_feedback_without_publishing(cli_settings: Settings) -> None:
    pending = VeraOrchestrator(cli_settings).analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(pending, ReviewRecord)

    rejected = CliRunner().invoke(
        app, ["review", pending.run_id, "--reject", "The evidence is insufficient"]
    )
    assert rejected.exit_code == 0
    assert "rejected" in rejected.stdout
    restored = VeraOrchestrator(cli_settings)
    assert restored.get_run(pending.run_id) is None
    assert restored.list_reviews() == []


def test_cli_revision_requires_external_provider(cli_settings: Settings) -> None:
    pending = VeraOrchestrator(cli_settings).analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(pending, ReviewRecord)

    revised = CliRunner().invoke(
        app, ["review", pending.run_id, "--revise", "Use the available evidence"]
    )
    assert revised.exit_code == 1
    assert "external model provider" in revised.output


def test_cli_interactive_review_approves(cli_settings: Settings) -> None:
    pending = VeraOrchestrator(cli_settings).analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(pending, ReviewRecord)

    approved = CliRunner().invoke(
        app, ["review", pending.run_id, "--interactive"], input="a\n"
    )
    assert approved.exit_code == 0
    assert "Unpublished draft" in approved.stdout
    assert VeraOrchestrator(cli_settings).get_review(pending.run_id).status == ReviewStatus.APPROVED


def test_cli_analyze_interactive_prompts_for_approval(cli_settings: Settings) -> None:

    approved = CliRunner().invoke(
        app,
        ["analyze", "Analyze CVE-2099-9999", "--offline", "--interactive"],
        input="a\n",
    )
    assert approved.exit_code == 0
    assert "Unpublished draft" in approved.stdout
    assert "Review required" not in approved.stdout


def test_cli_analyze_json_keeps_review_unpublished(cli_settings: Settings) -> None:

    result = CliRunner().invoke(
        app, ["analyze", "Analyze CVE-2099-9999", "--offline", "--json"]
    )
    assert result.exit_code == 2
    record = json.loads(result.stdout)
    assert record["status"] == ReviewStatus.PENDING
    assert VeraOrchestrator(cli_settings).get_run(record["run_id"]) is None


def test_cli_retries_interrupted_decision(cli_settings: Settings) -> None:
    engine = VeraOrchestrator(cli_settings)
    pending = engine.analyze({"query": "Analyze CVE-2099-9999"})
    assert isinstance(pending, ReviewRecord)
    decision = ReviewDecision(action="approve", version=0, decision_id=uuid4())
    engine.review_service.decisions.claim(pending.run_id, decision)

    errored = VeraOrchestrator(cli_settings).get_review(pending.run_id)
    assert errored is not None
    assert errored.status == ReviewStatus.ERROR
    assert errored.retry_decision == decision

    retried = CliRunner().invoke(app, ["review", pending.run_id, "--retry"])
    assert retried.exit_code == 0
    assert VeraOrchestrator(cli_settings).get_run(pending.run_id) is not None
