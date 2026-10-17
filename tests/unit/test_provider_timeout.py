import httpx
import pytest

from vera.config import Settings
from vera.domain.enums import Route
from vera.domain.reports import StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.errors import ProviderError
from vera.providers.factory import build_provider


@pytest.mark.parametrize("provider", ["openai", "ollama", "gemini"])
def test_slow_model_uses_its_own_timeout(monkeypatch, provider) -> None:
    settings = Settings(
        llm_provider=provider,
        llm_timeout_seconds=300,
        request_timeout_seconds=8,
        gemini_api_key="test-key",
    )
    observed = []

    def post(url, **kwargs):
        observed.append(kwargs["timeout"])
        content = '{"route":"CAG_ONLY"}'
        payload = (
            {"candidates": [{"content": {"parts": [{"text": content}]}}]}
            if provider == "gemini"
            else {"choices": [{"message": {"content": content}}]}
        )
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    assert build_provider(settings).classify("What is least privilege?") == Route.CAG_ONLY
    assert observed == [300]
    assert settings.request_timeout_seconds == 8


def test_lm_studio_receives_the_schema_for_each_task(monkeypatch) -> None:
    settings = Settings(
        llm_provider="openai", llm_response_format="json_schema", llm_reasoning_effort="low",
    )
    bodies = []

    def post(url, **kwargs):
        body = kwargs["json"]
        bodies.append(body)
        properties = body["response_format"]["json_schema"]["schema"]["properties"]
        if "route" in properties:
            content = '{"route":"CAG_ONLY"}'
        elif "action" in properties:
            content = '{"action":"finish","reason":"No further acquisition is required."}'
        else:
            content = '{"summary":"No evidence supplied.","claims":[],"out_of_scope":false}'
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    model = build_provider(settings)
    assert model.classify("What is least privilege?") == Route.CAG_ONLY
    result = model.generate(
        AnalysisRequest(query="What is least privilege?"), Route.CAG_ONLY,
        [], [], StreamStatistics(), [],
    )
    assert result.summary == "No evidence supplied."
    assert model.decide_action("Explain PowerShell", [], [], [], []).action == "finish"
    expected_fields = [
        {"route"}, {"summary", "claims", "out_of_scope"},
        {"action", "reason", "query", "cve_id"},
    ]
    for body, expected in zip(bodies, expected_fields, strict=True):
        assert body["response_format"]["type"] == "json_schema"
        assert body["reasoning_effort"] == "low"
        assert body["max_tokens"] == 1024
        schema = body["response_format"]["json_schema"]["schema"]
        assert set(schema["properties"]) == expected


def test_truncated_model_output_is_explicitly_rejected(monkeypatch) -> None:
    def post(url, **kwargs):
        return httpx.Response(
            200, json={"choices": [{"finish_reason": "length", "message": {"content": "{"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(ProviderError, match="output token limit"):
        build_provider(Settings(llm_provider="openai")).classify("Explain PowerShell")
