import asyncio

import httpx
from typer.testing import CliRunner

from vera.interfaces.api import create_app
from vera.interfaces.cli import app
from vera.workflow.orchestrator import VeraOrchestrator


def test_http_analysis_and_history(settings) -> None:
    orchestrator = VeraOrchestrator(settings)

    async def exercise_api() -> None:
        transport = httpx.ASGITransport(app=create_app(orchestrator=orchestrator))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["corpus_documents"] >= 60
            response = await client.post(
                "/v1/analyze",
                json={"query": "What is least privilege?"},
            )
            assert response.status_code == 200
            run_id = response.json()["run_id"]
            assert (await client.get(f"/v1/runs/{run_id}")).status_code == 200
            assert len((await client.get("/v1/runs")).json()) == 1
            corpus = await client.get("/v1/corpus")
            assert corpus.status_code == 200
            assert corpus.json()["total_documents"] >= 60

    asyncio.run(exercise_api())


def test_cli_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Vulnerability Evidence and Reasoning Agent" in result.stdout
