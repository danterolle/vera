import json
from pathlib import Path

from vera.evaluation.contract import named_review

ALLOWED = {
    "scope", "statuses_any", "statuses_none", "answer_any", "answer_none", "max_claims",
}
SCOPES = {"in", "out", "social"}
MIN_REVIEWED_CASES = 50
REQUIRED_TASKS = {
    "clarification", "concept_definition", "current_status", "defensive_guidance",
    "graph_evidence", "language_variant", "local_applicability", "memory_only",
    "missing_record", "multiturn_followup", "review_revision", "risk_comparison",
    "scope_boundary", "social_conversation", "stream_triage", "unavailable_concept",
    "untrusted_note", "vulnerability_triage",
}


def load_cases(path: Path) -> list[dict]:
    return parse_cases(path.read_text(encoding="utf-8"))


def parse_cases(source: str) -> list[dict]:
    cases, identifiers = [], set()
    for number, line in enumerate(source.splitlines(), 1):
        if not line.strip():
            continue
        case = json.loads(line)
        missing = {"id", "task", "query", "expect", "reviewed"} - set(case)
        if missing:
            raise ValueError(f"line {number}: missing {sorted(missing)}")
        if case["id"] in identifiers:
            raise ValueError(f"line {number}: duplicate id {case['id']}")
        identifiers.add(case["id"])
        if not isinstance(case["reviewed"], bool):
            raise ValueError(f"line {number}: reviewed must be boolean")
        if case["reviewed"] and not named_review(case):
            raise ValueError(f"line {number}: reviewed cases need a human reviewer and date")
        unknown = set(case["expect"]) - ALLOWED
        if unknown:
            raise ValueError(f"line {number}: unknown expect keys {sorted(unknown)}")
        if case["expect"].get("scope") not in SCOPES:
            raise ValueError(f"line {number}: scope must be one of {sorted(SCOPES)}")
        cases.append(case)
    if not cases:
        raise ValueError("Golden case set is empty")
    return cases
