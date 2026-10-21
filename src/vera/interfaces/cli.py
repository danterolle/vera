import json
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from vera.config import Settings
from vera.domain.requests import AnalysisRequest
from vera.domain.review import ReviewRecord
from vera.errors import VeraError
from vera.evaluation.runner import run_evaluation
from vera.interfaces.api import create_app
from vera.interfaces.knowledge_graph import register_commands as register_graph_commands
from vera.interfaces.local_access import is_loopback
from vera.interfaces.review_cli import prompt_review
from vera.interfaces.review_cli import register_commands as register_review_commands
from vera.retrieval.corpus import LocalCorpus
from vera.retrieval.embeddings import build_embedder
from vera.retrieval.models import CorpusFeed
from vera.retrieval.store import CorpusStore
from vera.retrieval.sync import CorpusSynchronizer
from vera.stream.parsers import load_events
from vera.stream.pcap import PcapExtractor
from vera.workflow.orchestrator import VeraOrchestrator

app = typer.Typer(
    name="vera",
    help="Vulnerability Evidence and Reasoning Agent.",
    no_args_is_help=True,
)
register_graph_commands(app)
register_review_commands(app)


@app.command()
def analyze(
    query: Annotated[str, typer.Argument(help="Cybersecurity question or analysis request.")],
    events: Annotated[
        Path | None,
        typer.Option("--events", help="Normalized .json or .jsonl event file."),
    ] = None,
    pcap: Annotated[
        Path | None,
        typer.Option("--pcap", help="Controlled .pcap, .pcapng, or .cap replay."),
    ] = None,
    offline: Annotated[
        bool,
        typer.Option("--offline", help="Disable live authoritative source lookups."),
    ] = False,
    simulated: Annotated[
        bool,
        typer.Option("--simulated", help="Label supplied events as simulated."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the complete JSON result."),
    ] = False,
    interactive: Annotated[
        bool | None,
        typer.Option(
            "--interactive/--no-interactive",
            help="Prompt for a human review decision in an interactive terminal.",
        ),
    ] = None,
) -> None:
    if events is not None and pcap is not None:
        raise typer.BadParameter("Use either --events or --pcap, not both")
    if json_output and interactive:
        raise typer.BadParameter("--json cannot be combined with --interactive")
    settings = Settings()
    if offline:
        settings = settings.model_copy(update={"live_sources": False})
    engine = VeraOrchestrator(settings)
    try:
        normalized = load_events(events, settings.max_events) if events else []
        if pcap is not None:
            normalized = PcapExtractor(settings.max_events).extract(pcap)
        if simulated:
            normalized = [event.model_copy(update={"simulated": True}) for event in normalized]
        result = engine.analyze(
            AnalysisRequest(query=query, events=normalized, simulated=simulated)
        )
    except (VeraError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if isinstance(result, ReviewRecord):
        if json_output:
            typer.echo(result.model_dump_json(indent=2))
            raise typer.Exit(code=2)
        prompt_human = interactive if interactive is not None else sys.stdin.isatty()
        if prompt_human:
            prompt_review(engine, result)
        typer.echo(
            f"Review required for {result.run_id}. Open /graph on the local VERA server "
            f"or run: vera review {result.run_id}"
        )
        raise typer.Exit(code=2)
    typer.echo(result.model_dump_json(indent=2) if json_output else result.answer)


@app.command("evaluate")
def evaluate_command(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit the complete JSON report."),
    ] = False,
) -> None:
    report = run_evaluation(Settings(live_sources=False))
    if json_output:
        typer.echo(report.model_dump_json(indent=2))
    else:
        typer.echo(
            f"Passed: {report.passed}\n"
            f"Routing accuracy: {report.routing_accuracy:.1%}\n"
            f"Retrieval success: {report.retrieval_success_rate:.1%}\n"
            f"Detector accuracy: {report.detector_accuracy:.1%}\n"
            f"Grounding rate: {report.grounding_rate:.1%}\n"
            f"Average source coverage: {report.average_source_coverage:.1%}\n"
            f"Average latency: {report.average_latency_ms:.2f} ms\n"
            f"Model calls: {report.total_model_calls}\n"
            f"Tool calls: {report.total_tool_calls}"
        )
    if not report.passed:
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Bind port.", min=1, max=65535)] = 8000,
    open_browser: Annotated[
        bool,
        typer.Option("--open-browser", help="Open the local LangGraph visualization."),
    ] = False,
) -> None:
    if not is_loopback(host):
        raise typer.BadParameter("Review-enabled VERA serves only on a loopback address")
    if open_browser:
        browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        timer = threading.Timer(
            0.8,
            lambda: webbrowser.open(f"http://{browser_host}:{port}/graph"),
        )
        timer.daemon = True
        timer.start()
    uvicorn.run(create_app(), host=host, port=port)


@app.command()
def history(
    limit: Annotated[int, typer.Option(min=1, max=100)] = 10,
) -> None:
    runs = VeraOrchestrator().list_runs(limit)
    typer.echo(
        json.dumps(
            [
                {
                    "run_id": item.run_id,
                    "created_at": item.created_at.isoformat(),
                    "route": item.route.value,
                    "completeness": item.reflection.completeness_score,
                }
                for item in runs
            ],
            indent=2,
        )
    )


@app.command("corpus-status")
def corpus_status() -> None:
    settings = Settings()
    try:
        embedder = build_embedder(settings)
        store = CorpusStore(settings.corpus_dir, settings.max_corpus_documents)
        status = LocalCorpus(embedder, store, settings.retrieval_min_score).status()
    except VeraError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(status.model_dump_json(indent=2))


@app.command("corpus-sync")
def corpus_sync(
    feed: Annotated[
        CorpusFeed,
        typer.Option(help="Authoritative feed to synchronize."),
    ] = CorpusFeed.ALL,
) -> None:
    settings = Settings()
    try:
        report = CorpusSynchronizer(settings).sync(feed)
    except VeraError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(report.model_dump_json(indent=2))
