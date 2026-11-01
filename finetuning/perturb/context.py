"""Parse and rewrite the structured context embedded in VERA prompts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

CVE = re.compile(r"CVE-\d{4}-\d{4,7}")


@dataclass(frozen=True)
class PromptContext:
    """One dataset example, split around its embedded JSON context."""

    task: str
    system: str
    prefix: str
    suffix: str
    data: dict
    user: str

    def render(self, data: dict) -> str:
        return self.prefix + json.dumps(data) + self.suffix

    @property
    def cves(self) -> list[str]:
        return list(dict.fromkeys(CVE.findall(self.user)))


def load_example(example: dict) -> PromptContext:
    user = example["messages"][1]["content"]
    start = user.find("{")
    if start < 0:
        raise ValueError(f"example {example.get('id')!r} has no JSON context")
    data, end = json.JSONDecoder().raw_decode(user[start:])
    return PromptContext(
        task=example["task"],
        system=example["messages"][0]["content"],
        prefix=user[:start],
        suffix=user[start + end :],
        data=data,
        user=user,
    )


def build_case(
    context: PromptContext, family: str, data: dict, checks: dict, index: int
) -> dict:
    return {
        "id": f"pert-{family}-{index:03d}",
        "task": context.task,
        "family": family,
        "messages": [
            {"role": "system", "content": context.system},
            {"role": "user", "content": context.render(data)},
            {"role": "assistant", "content": ""},
        ],
        "checks": checks,
    }


def group_by_task(contexts: list[PromptContext]) -> dict[str, list[PromptContext]]:
    grouped: dict[str, list[PromptContext]] = {}
    for context in contexts:
        grouped.setdefault(context.task, []).append(context)
    return grouped


def set_question(data: dict, question: str) -> None:
    """Replace the user question, keeping optional mirrors aligned when present."""

    data["query"] = question
    for key in ("resolved_question", "research_query"):
        if key in data:
            data[key] = question
