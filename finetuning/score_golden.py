"""Score model answers against golden cases with deterministic fact and scope checks."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from vera_finetuning.evaluation import extract_json

ALLOWED = {
    "scope", "statuses_any", "statuses_none", "answer_any", "answer_none", "max_claims",
}
SCOPES = {"in", "out", "social"}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def contains(text: str, term: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(normalize(term))}(?![a-z0-9])"
    return re.search(pattern, text) is not None


def load_cases(path: Path) -> list[dict]:
    cases, identifiers = [], set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
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
        unknown = set(case["expect"]) - ALLOWED
        if unknown:
            raise ValueError(f"line {number}: unknown expect keys {sorted(unknown)}")
        if case["expect"].get("scope") not in SCOPES:
            raise ValueError(f"line {number}: scope must be one of {sorted(SCOPES)}")
        cases.append(case)
    return cases


def evaluate(case: dict, payload: dict | None) -> list[str]:
    if payload is None:
        return ["answer does not contain valid JSON"]
    expect = case["expect"]
    claims = payload.get("claims") or []
    if not isinstance(claims, list):
        return ["claims is not a list"]
    text = normalize(json.dumps(payload, ensure_ascii=False))
    failures = []
    scope = expect["scope"]
    out_of_scope = payload.get("out_of_scope")
    if scope == "out":
        if out_of_scope is not True:
            failures.append("expected out_of_scope=true")
        if claims:
            failures.append("unrelated request returned claims")
    else:
        if out_of_scope is not False:
            failures.append("expected out_of_scope=false")
        if scope == "social" and claims:
            failures.append("social message returned claims")
    statuses = {claim.get("status") for claim in claims if isinstance(claim, dict)}
    required_any = set(expect.get("statuses_any", []))
    if required_any and not statuses & required_any:
        failures.append(f"missing status in {sorted(required_any)}")
    forbidden = set(expect.get("statuses_none", []))
    if statuses & forbidden:
        failures.append(f"forbidden status in {sorted(statuses & forbidden)}")
    for group in expect.get("answer_any", []):
        if not any(contains(text, term) for term in group):
            failures.append(f"missing any of {group}")
    for term in expect.get("answer_none", []):
        if contains(text, term):
            failures.append(f"forbidden term {term!r}")
    maximum = expect.get("max_claims")
    if maximum is not None and len(claims) > maximum:
        failures.append(f"{len(claims)} claims exceed {maximum}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=Path("finetuning/golden/cases.jsonl"),
    )
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--include-draft", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Choose a new report path; existing reports are never overwritten")
    cases = load_cases(args.cases)
    reviewed = [case for case in cases if case["reviewed"]]
    drafts = [case for case in cases if not case["reviewed"]]
    selected = cases if args.include_draft else reviewed
    by_case = {case["id"]: case for case in selected}
    answers = defaultdict(dict)
    for number, line in enumerate(args.answers.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if "id" not in row or "answer" not in row:
            raise ValueError(f"answers line {number}: id and answer are required")
        answers[row.get("model", "unknown")][row["id"]] = row["answer"]
    report = {
        "cases": len(cases),
        "reviewed": len(reviewed),
        "drafts_excluded": 0 if args.include_draft else len(drafts),
        "draft_warning": None if args.include_draft else (
            "Drafts are format examples, not evidence; pass --include-draft to inspect them."
        ),
        "models": {},
    }
    for model, rows in sorted(answers.items()):
        results, passed = [], 0
        for identifier, case in by_case.items():
            answer = rows.get(identifier)
            payload = extract_json(answer) if isinstance(answer, str) else None
            failures = ["missing answer"] if answer is None else evaluate(case, payload)
            passed += not failures
            results.append({
                "id": identifier,
                "task": case["task"],
                "reviewed": case["reviewed"],
                "passed": not failures,
                "failures": failures,
            })
        results.sort(key=lambda item: (item["task"], item["id"]))
        report["models"][model] = {
            "selected_cases": len(by_case),
            "passed": passed,
            "results": results,
        }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
