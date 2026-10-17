import json

import httpx
from pydantic import ValidationError

from vera.domain.actions import ReActAction, ReActObservation
from vera.domain.enums import Route
from vera.domain.evidence import Evidence
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.errors import ProviderError
from vera.providers.prompts import SYSTEM_PROMPT, generation_prompt, routing_prompt
from vera.providers.react import ACTION_SYSTEM_PROMPT, action_prompt


class HttpModelProvider:
    external = True

    def __init__(self, name: str, model: str) -> None:
        self.name = name
        self.model = model

    def classify(self, query: str) -> Route:
        schema = {
            "type": "object",
            "properties": {"route": {"type": "string", "enum": [
                route.value for route in Route if route not in {Route.STREAM, Route.FULL}
            ]}},
            "required": ["route"],
            "additionalProperties": False,
        }
        content = self._complete(routing_prompt(query), SYSTEM_PROMPT, schema)
        try:
            return Route(_json_object(content)["route"])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError(f"{self.name} returned an invalid route") from exc

    def generate(
        self,
        request: AnalysisRequest,
        route: Route,
        evidence: list[Evidence],
        alerts: list[DetectionAlert],
        statistics: StreamStatistics,
        feedback: list[str],
    ) -> GeneratedAnswer:
        prompt = generation_prompt(request, route, evidence, alerts, statistics, feedback)
        schema = GeneratedAnswer.model_json_schema()
        schema["required"] = [*schema.get("required", []), "out_of_scope"]
        content = self._complete(prompt, SYSTEM_PROMPT, schema)
        try:
            return GeneratedAnswer.model_validate(_json_object(content))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ProviderError(f"{self.name} returned an invalid analysis payload") from exc

    def decide_action(
        self,
        query: str,
        evidence: list[Evidence],
        cve_ids: list[str],
        observations: list[ReActObservation],
        searched_queries: list[str],
    ) -> ReActAction:
        content = self._complete(
            action_prompt(query, evidence, cve_ids, observations, searched_queries),
            ACTION_SYSTEM_PROMPT,
            ReActAction.model_json_schema(),
        )
        try:
            return ReActAction.model_validate(_json_object(content))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ProviderError(f"{self.name} returned an invalid ReAct action") from exc

    def _complete(self, prompt: str, system: str, schema: dict) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(HttpModelProvider):
    def __init__(
        self,
        name: str,
        model: str,
        base_url: str,
        api_key: str | None,
        timeout: float,
        response_format: str = "json_object",
        reasoning_effort: str | None = None,
        max_output_tokens: int = 1024,
    ) -> None:
        super().__init__(name, model)
        normalized_url = base_url.rstrip("/")
        suffix = "/chat/completions" if normalized_url.endswith("/v1") else "/v1/chat/completions"
        self.endpoint = f"{normalized_url}{suffix}"
        self.api_key = api_key
        self.timeout = timeout
        self.response_format = response_format
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens

    def _complete(self, prompt: str, system: str, schema: dict) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response_format = {"type": self.response_format}
        if self.response_format == "json_schema":
            response_format["json_schema"] = {"name": "vera_response", "schema": schema}
        try:
            response = httpx.post(
                self.endpoint,
                headers=headers,
                timeout=self.timeout,
                json={
                    "model": self.model,
                    "temperature": 0,
                    "max_tokens": self.max_output_tokens,
                    "response_format": response_format,
                    **({"reasoning_effort": self.reasoning_effort}
                       if self.reasoning_effort is not None else {}),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ProviderError(f"{self.name} exceeded the output token limit")
            return choice["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"{self.name} request failed: {exc}") from exc


class GeminiProvider(HttpModelProvider):
    def __init__(self, model: str, api_key: str, timeout: float) -> None:
        super().__init__("gemini", model)
        self.endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )
        self.api_key = api_key
        self.timeout = timeout

    def _complete(self, prompt: str, system: str, schema: dict) -> str:
        try:
            response = httpx.post(
                self.endpoint,
                params={"key": self.api_key},
                timeout=self.timeout,
                json={
                    "system_instruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0,
                        "responseMimeType": "application/json",
                    },
                },
            )
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"gemini request failed: {exc}") from exc


def _json_object(content: str) -> dict:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        raise json.JSONDecodeError("No JSON object found", content, 0)
    value = json.loads(content[start : end + 1])
    if not isinstance(value, dict):
        raise json.JSONDecodeError("Expected a JSON object", content, start)
    return value
