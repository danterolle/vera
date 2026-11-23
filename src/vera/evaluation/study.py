import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from vera.data import resource
from vera.domain.requests import AnalysisRequest
from vera.evaluation.contract import used_fallback
from vera.evaluation.golden import MIN_REVIEWED_CASES, REQUIRED_TASKS, parse_cases
from vera.evaluation.review_pack import case_key, load_jsonl
from vera.interfaces.local_access import is_loopback
from vera.reasoning.validation import VALIDATION_CONTRACT

REQUEST_KEYS = ("query", "conversation", "events", "simulated")
SAMPLES = {
    "benign-web.jsonl", "http-brute-force.jsonl", "network-events.jsonl",
    "port-scan.jsonl", "syn-flood.jsonl", "web-exploitation.jsonl",
}
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class StudyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    golden_sha256: str = Field(pattern=SHA256_PATTERN)
    queries_sha256: str = Field(pattern=SHA256_PATTERN)
    validation_contract: str
    cases: int = Field(ge=MIN_REVIEWED_CASES)


def _query_row(case: dict) -> dict:
    if not isinstance(case["id"], str) or not re.fullmatch(r"[a-z0-9-]{1,100}", case["id"]):
        raise ValueError("Case IDs must use 1-100 lowercase ASCII letters, digits or hyphens")
    raw = {key: case[key] for key in REQUEST_KEYS if key in case}
    if "events_file" in case:
        sample = case["events_file"]
        if sample not in SAMPLES or "events" in raw:
            raise ValueError(f"{case['id']}: use one bundled event sample or inline events")
        raw["events"] = [
            json.loads(line)
            for line in resource(f"samples/{sample}").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        raw["simulated"] = True
    if raw.get("events") and (
        raw.get("simulated") is not True or any("timestamp" not in event for event in raw["events"])
    ):
        raise ValueError(f"{case['id']}: event inputs must be simulated and timestamped")
    request = AnalysisRequest.model_validate(raw)
    return {
        "id": case["id"],
        "task": case["task"],
        "expect_scope": case["expect"]["scope"],
        **request.model_dump(mode="json", include=set(raw)),
        "rubric": case["expect"],
        "note": case.get("notes", ""),
        "case_review": {key: case[key] for key in ("reviewer", "reviewed_at")},
    }


def prepare(args: argparse.Namespace) -> None:
    source = args.cases.read_bytes()
    cases = parse_cases(source.decode("utf-8"))
    drafts = [case["id"] for case in cases if not case["reviewed"]]
    if drafts:
        raise ValueError(f"Human case review is required before preparation ({len(drafts)} drafts)")
    tasks = {case["task"] for case in cases}
    if len(cases) < MIN_REVIEWED_CASES or tasks != REQUIRED_TASKS:
        raise ValueError(
            f"Use at least {MIN_REVIEWED_CASES} reviewed cases across the golden tasks; "
            f"missing: {sorted(REQUIRED_TASKS - tasks)}; unknown: {sorted(tasks - REQUIRED_TASKS)}"
        )
    rows = [_query_row(case) for case in cases]
    if len({case_key(row) for row in rows}) != len(rows):
        raise ValueError("Golden cases contain duplicate runtime requests")
    queries = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()
    manifest = StudyManifest(
        model=args.model,
        artifact_sha256=args.artifact_sha256,
        golden_sha256=hashlib.sha256(source).hexdigest(),
        queries_sha256=hashlib.sha256(queries).hexdigest(),
        validation_contract=VALIDATION_CONTRACT,
        cases=len(rows),
    )
    args.output.mkdir(parents=True)
    (args.output / "queries.jsonl").write_bytes(queries)
    (args.output / "study.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    print(f"Prepared {len(rows)} reviewed cases in {args.output}")


def read_study(path: Path) -> tuple[StudyManifest, list[dict]]:
    manifest = StudyManifest.model_validate_json((path / "study.json").read_text(encoding="utf-8"))
    if manifest.validation_contract != VALIDATION_CONTRACT:
        raise ValueError("The study was prepared for a different validation contract")
    content = (path / "queries.jsonl").read_bytes()
    if hashlib.sha256(content).hexdigest() != manifest.queries_sha256:
        raise ValueError("The prepared queries have changed")
    rows = [json.loads(line) for line in content.splitlines() if line.strip()]
    if len(rows) != manifest.cases:
        raise ValueError("The prepared case count does not match the manifest")
    return manifest, rows


def verify_answers(path: Path, answer_path: Path) -> tuple[dict, list[dict]]:
    manifest, queries = read_study(path)
    answers = load_jsonl(answer_path)
    by_id = {row["id"]: row for row in answers}
    if len(by_id) != len(answers) or set(by_id) != {row["id"] for row in queries}:
        raise ValueError("The answer file must cover every prepared case exactly once")
    rows = []
    study = manifest.model_dump()
    for query in queries:
        answer = by_id[query["id"]]
        if answer.get("study") != study:
            raise ValueError(f"{query['id']}: the answer belongs to a different study")
        if any(query.get(key) != answer.get(key) for key in REQUEST_KEYS):
            raise ValueError(f"{query['id']}: the answer does not match the prepared request")
        verify_model(manifest, query["id"], answer["result"])
        rows.append({**query, **{key: answer[key] for key in ("http_status", "seconds", "result")}})
    return study, rows


def verify_model(manifest: StudyManifest, case_id: str, result: dict) -> None:
    metadata = result.get("metadata", {})
    if metadata.get("validation_contract") != manifest.validation_contract:
        raise ValueError(f"{case_id}: the answer did not use the study's validation contract")
    if not used_fallback({"result": result}) and metadata.get("model") != manifest.model:
        raise ValueError(f"{case_id}: the answer did not come from the declared model ID")


def require_loopback(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"} or not is_loopback(parsed.hostname)
        or parsed.username is not None or parsed.password is not None
        or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.port == 0
    ):
        raise ValueError("A prepared study must use a loopback VERA server URL")
