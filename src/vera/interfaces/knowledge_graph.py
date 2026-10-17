import json
from pathlib import Path
from typing import Annotated

import typer

from vera.config import Settings
from vera.errors import VeraError
from vera.knowledge_graph.store import KnowledgeGraphStore
from vera.knowledge_graph.view import graph_view
from vera.memory.graph_jobs import project_pending
from vera.memory.store import MemoryStore
from vera.retrieval.corpus import LocalCorpus
from vera.retrieval.embeddings import build_embedder
from vera.retrieval.knowledge import CuratedKnowledge
from vera.retrieval.store import CorpusStore


def register_commands(app: typer.Typer) -> None:
    app.command("kg-build")(build)
    app.command("kg-status")(status)
    app.command("kg-export")(export)


def build() -> None:
    """Incrementally import the local corpus and replay retained graph projection jobs."""
    settings = Settings()
    try:
        embedder = build_embedder(settings)
        corpus = LocalCorpus(
            embedder,
            CorpusStore(settings.corpus_dir, settings.max_corpus_documents),
        )
        graph = KnowledgeGraphStore(settings)
        graph.build(CuratedKnowledge().documents + corpus.documents)
        jobs = project_pending(MemoryStore(settings.db_path, embedder), graph, replay=True)
        result = graph.status().model_dump()
        result["projected_runs"] = jobs
        typer.echo(json.dumps(result, indent=2))
    except VeraError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def status() -> None:
    """Inspect the database without creating or changing it."""
    report = KnowledgeGraphStore(Settings()).status()
    typer.echo(report.model_dump_json(indent=2))
    if not report.available:
        raise typer.Exit(code=1)


def export(
    output: Annotated[
        Path,
        typer.Option(help="Write a bounded JSON graph view."),
    ] = Path("knowledge-graph.json"),
    identifier: Annotated[str | None, typer.Option("--id", help="Exact entity identifier.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 50,
) -> None:
    """Export a graph neighborhood for inspection (not a database backup)."""
    try:
        view = graph_view(KnowledgeGraphStore(Settings()), identifier, limit)
        if not view.status.available:
            typer.echo(view.status.error, err=True)
            raise typer.Exit(code=1)
        output.write_text(view.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(str(output.resolve()))
    except (VeraError, ValueError, OSError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
