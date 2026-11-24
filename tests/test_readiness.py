from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx
from pydantic import SecretStr

from vera.config import Settings
from vera.interfaces.api import create_app
from vera.workflow.orchestrator import VeraOrchestrator


class ReadinessTests(IsolatedAsyncioTestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.settings = Settings(
            _env_file=None,
            db_path=Path(directory) / "test.db",
            corpus_dir=Path(directory) / "corpus",
            llm_provider="deterministic",
            live_sources=False,
            kg_enabled=False,
            react_enabled=False,
            embedding_backend="hash",
        )

    async def client(self, provider: str = "deterministic") -> httpx.AsyncClient:
        settings = self.settings.model_copy(update={
            "llm_provider": provider, "gemini_api_key": SecretStr("test-key"),
        })
        engine = self.enterContext(VeraOrchestrator(settings))
        return await self.enterAsyncContext(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(orchestrator=engine)),
            base_url="http://127.0.0.1",
        ))

    async def test_deterministic_readiness_does_not_call_a_model(self):
        client = await self.client()
        with patch("vera.providers.http.httpx.post") as post:
            response = await client.get("/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready", "model_probe": "not_required"})
        post.assert_not_called()

    async def test_external_readiness_sends_one_synthetic_request_without_saving(self):
        client = await self.client("openai")
        with patch("vera.providers.http.httpx.post") as post:
            post.return_value.json.return_value = {
                "choices": [{"message": {"content": '{"ready":true}'}}],
            }
            self.assertEqual((await client.get("/ready")).json(), {
                "status": "ready", "model_probe": "passed",
            })
        post.assert_called_once()
        self.assertLessEqual(post.call_args.kwargs["timeout"], 5)
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(messages[-1]["content"], 'Return {"ready":true}.')
        self.assertEqual((await client.get("/v1/runs")).json(), [])

    async def test_unavailable_and_invalid_model_responses_are_not_ready(self):
        client = await self.client("openai")
        with patch("vera.providers.http.httpx.post") as post:
            post.side_effect = httpx.ConnectError("Model offline")
            self.assertEqual((await client.get("/health")).status_code, 200)
            self.assertEqual((await client.get("/ready")).status_code, 503)
            post.side_effect = None
            for payload in (
                {"choices": []},
                {"choices": [{"message": {"content": '{"ready":1}'}}]},
            ):
                with self.subTest(payload=payload):
                    post.return_value.json.return_value = payload
                    self.assertEqual((await client.get("/ready")).status_code, 503)

    async def test_gemini_readiness_uses_the_same_model_completion_parser(self):
        client = await self.client("gemini")
        with patch("vera.providers.http.httpx.post") as post:
            post.return_value.json.return_value = {
                "candidates": [{"content": {"parts": [{"text": '{"ready":true}'}]}}],
            }
            self.assertEqual((await client.get("/ready")).status_code, 200)
            post.return_value.json.return_value = {"candidates": []}
            self.assertEqual((await client.get("/ready")).status_code, 503)
