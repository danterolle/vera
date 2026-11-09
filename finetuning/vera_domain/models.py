import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vera.domain.enums import SourceType
from vera.domain.reports import GeneratedAnswer


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class SourceFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    entity_id: str
    family: str
    category: str
    source: SourceType
    title: str
    content: str = Field(min_length=20, max_length=900)
    original: str
    field_path: str
    source_url: str
    snapshot: str
    revision: str
    tags: list[str] = Field(default_factory=list)


class ScenarioMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: str
    entities: list[str] = Field(default_factory=list)
    source_bindings: dict[str, str] = Field(default_factory=dict)
    detector_family: str | None = None
    window_case: str | None = None
    feedback_kind: str | None = None
    event_replay_id: str | None = None
    alert_count: int = 0
    conversation_turns: int = 0
    language: str = "English"
    intent: str = "cybersecurity"


class TrainingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task: str
    groups: list[str]
    source_ids: list[str]
    origin: Literal["source_grounded_synthetic"] = "source_grounded_synthetic"
    scenario: ScenarioMetadata
    messages: list[Message]


def fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def context_from_prompt(prompt: str) -> dict:
    context, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("{"):])
    if not isinstance(context, dict):
        raise ValueError("The generation context must be an object")
    return context


def parsed_answer(record: TrainingRecord) -> GeneratedAnswer:
    return GeneratedAnswer.model_validate_json(record.messages[-1].content)


def semantic_fingerprint(record: TrainingRecord) -> str:
    if isinstance(record, dict):
        record = TrainingRecord.model_validate(record)
    context = context_from_prompt(record.messages[1].content)
    evidence = [
        {key: value for key, value in item.items() if key != "id"}
        for item in context["evidence"]
    ]
    return fingerprint({
        "task": record.task,
        "query": context["query"],
        "conversation": context["conversation"],
        "evidence": sorted(evidence, key=lambda item: json.dumps(item, sort_keys=True)),
        "alerts": context["alerts"],
        "statistics": context["statistics"],
        "feedback": context["feedback"],
    })
