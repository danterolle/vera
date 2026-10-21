import asyncio
from uuid import uuid4

import httpx
from typer.testing import CliRunner

from vera.domain.review import ReviewRecord, ReviewStatus
from vera.interfaces.api import create_app
from vera.interfaces.cli import app
from vera.workflow.orchestrator import VeraOrchestrator


def test_pending_review_api_does_not_publish_before_approval(settings) -> None:
    engine = VeraOrchestrator(settings)

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=create_app(orchestrator=engine))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            ordinary = await client.post("/v1/analyze", json={"query": "What is least privilege?"})
            assert ordinary.status_code == 200
            assert ordinary.json()["answer"]
            assert (await client.get("/v1/reviews")).json() == []
            response = await client.post("/v1/analyze", json={"query": "Analyze CVE-2099-9999"})
            assert response.status_code == 202
            record = response.json()
            run_id = record["run_id"]
            assert record["status"] == ReviewStatus.PENDING
            assert record["reasons"]
            assert record["draft"]["summary"]
            assert (await client.get(f"/v1/runs/{run_id}")).status_code == 404
            assert (await client.get(f"/v1/graph?run_id={run_id}")).status_code == 404
            assert len((await client.get("/v1/reviews")).json()) == 1
            assert (await client.get(f"/v1/reviews/{run_id}")).json() == record
            choice = {"action": "approve", "version": 0, "decision_id": str(uuid4())}
            accepted = await client.post(f"/v1/reviews/{run_id}/decisions", json=choice)
            assert accepted.status_code == 200
            assert accepted.json()["run_id"] == run_id
            assert (await client.get(f"/v1/runs/{run_id}")).status_code == 200
            repeated = await client.post(f"/v1/reviews/{run_id}/decisions", json=choice)
            assert repeated.status_code == 200
            assert repeated.json() == accepted.json()
            reused = {**choice, "action": "reject", "feedback": "Different decision"}
            conflict = await client.post(f"/v1/reviews/{run_id}/decisions", json=reused)
            assert conflict.status_code == 409
            stale = await client.post(
                f"/v1/reviews/{run_id}/decisions",
                json={
                    "action": "reject",
                    "version": 0,
                    "decision_id": str(uuid4()),
                    "feedback": "Outdated decision",
                },
            )
            assert stale.status_code == 409

    asyncio.run(exercise())


def test_rejection_requires_feedback_and_never_publishes(settings) -> None:
    engine = VeraOrchestrator(settings)

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=create_app(orchestrator=engine))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://localhost"
        ) as client:
            review = (
                await client.post("/v1/analyze", json={"query": "Analyze CVE-2099-9999"})
            ).json()
            path = f"/v1/reviews/{review['run_id']}/decisions"
            choice = {"action": "reject", "version": 0, "decision_id": str(uuid4())}
            assert (await client.post(path, json=choice)).status_code == 422
            rejected = await client.post(path, json={**choice, "feedback": "Not reliable"})
            assert rejected.status_code == 200
            assert rejected.json()["status"] == ReviewStatus.REJECTED
            assert (await client.get(f"/v1/runs/{review['run_id']}")).status_code == 404
            assert (await client.get("/v1/reviews")).json() == []

    asyncio.run(exercise())


def test_local_access_and_json_decisions_are_enforced(settings) -> None:
    engine = VeraOrchestrator(settings)

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=create_app(orchestrator=engine))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            run = (
                await client.post("/v1/analyze", json={"query": "Analyze CVE-2099-9999"})
            ).json()
            path = f"/v1/reviews/{run['run_id']}/decisions"
            assert (await client.post(path, content="{}")).status_code == 415
            headers = {"Origin": "http://untrusted.example"}
            assert (await client.get("/v1/reviews", headers=headers)).status_code == 403
            assert (await client.post(path, json={}, headers=headers)).status_code == 403
            assert (
                await client.get("/v1/reviews", headers={"Host": "untrusted.example"})
            ).status_code == 403
            assert (
                await client.get("/v1/reviews", headers={"Host": "evil@localhost"})
            ).status_code == 403
        remote = httpx.ASGITransport(
            app=create_app(orchestrator=engine), client=("203.0.113.9", 5182)
        )
        async with httpx.AsyncClient(
            transport=remote, base_url="http://127.0.0.1"
        ) as client:
            assert (await client.get("/v1/reviews")).status_code == 403

    asyncio.run(exercise())


def test_open_review_listing_includes_older_than_fifty(settings) -> None:
    engine = VeraOrchestrator(settings)
    reviews = [
        engine.analyze({"query": f"Analyze CVE-2099-{10000 + index}"})
        for index in range(53)
    ]
    assert all(isinstance(record, ReviewRecord) for record in reviews)

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=create_app(orchestrator=engine))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1"
        ) as client:
            response = await client.get("/v1/reviews")
            assert response.status_code == 200
            listed = response.json()
            assert len(listed) == 53
            assert listed[0]["run_id"] == reviews[-1].run_id
            assert listed[-1]["run_id"] == reviews[0].run_id
            oldest = await client.get(f"/v1/reviews/{reviews[0].run_id}")
            assert oldest.status_code == 200

    asyncio.run(exercise())


def test_cli_reports_pending_without_presenting_a_final_answer(settings, monkeypatch) -> None:
    monkeypatch.setattr("vera.interfaces.cli.Settings", lambda: settings)
    result = CliRunner().invoke(app, ["analyze", "Analyze CVE-2099-9999", "--offline"])
    assert result.exit_code == 2
    assert "Review required" in result.stdout
    assert "Open /graph" in result.stdout


def test_server_rejects_non_loopback_binding() -> None:
    result = CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code != 0
    assert "loopback" in result.output
