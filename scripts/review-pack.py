"""Generate and review runtime answers without training or authorizing deployment."""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from vera.evaluation.review_pack import build, case_key, load_jsonl
from vera.evaluation.review_verdicts import record, summarize
from vera.evaluation.study import (
    REQUEST_KEYS,
    prepare,
    read_study,
    require_loopback,
    verify_answers,
    verify_model,
)


def generate(args: argparse.Namespace) -> None:
    manifest = None
    if args.study is not None:
        require_loopback(args.url)
        manifest, queries = read_study(args.study)
    else:
        queries = load_jsonl(args.queries)
    study = manifest.model_dump() if manifest is not None else None
    if (
        not queries or len({row["id"] for row in queries}) != len(queries)
        or len({case_key(row) for row in queries}) != len(queries)
    ):
        raise ValueError("Queries must contain unique cases and cannot be empty")
    output = args.output
    previous = load_jsonl(output) if output.exists() else []
    done = {row["id"]: row for row in previous}
    by_id = {row["id"]: row for row in queries}
    if len(done) != len(previous) or done.keys() - by_id.keys():
        raise ValueError("Existing answers contain duplicate or unexpected cases")
    for identifier, row in done.items():
        if any(row.get(key) != by_id[identifier].get(key) for key in (
            *REQUEST_KEYS, "task", "expect_scope",
        )):
            raise ValueError(f"{identifier}: cannot resume with different case inputs")
        if manifest is not None:
            if row.get("study") != study:
                raise ValueError(f"{identifier}: cannot resume a different study")
            verify_model(manifest, identifier, row["result"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with (
        httpx.Client(timeout=args.timeout, trust_env=manifest is None) as client,
        output.open("a", encoding="utf-8") as stream,
    ):
        for query in queries:
            if query["id"] in done:
                continue
            started = time.monotonic()
            prefix = f"review-{manifest.queries_sha256[:12]}" if manifest else "review"
            response = client.post(
                args.url.rstrip("/") + "/v1/analyze",
                json={
                    "query": query["query"], "session_id": f"{prefix}-{query['id']}",
                    **{key: query[key] for key in REQUEST_KEYS if key != "query" and key in query},
                },
            )
            seconds = round(time.monotonic() - started, 2)
            if response.status_code not in {200, 202}:
                raise SystemExit(
                    f"{query['id']}: HTTP {response.status_code}: {response.text[:300]}"
                )
            result = response.json()
            if manifest is not None:
                verify_model(manifest, query["id"], result)
            stream.write(json.dumps({
                **query, "http_status": response.status_code,
                "seconds": seconds, "result": result,
                **({"study": study} if study is not None else {}),
            }, ensure_ascii=False) + "\n")
            stream.flush()
            print(f"{query['id']} {response.status_code} {seconds:.1f}s", file=sys.stderr)


def build_pack(args: argparse.Namespace) -> None:
    if args.study is None:
        build(args)
    else:
        study, rows = verify_answers(args.study, args.answers)
        build(args, rows=rows, study=study)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("prepare", help="Freeze reviewed golden cases for a local model study")
    setup.add_argument("--cases", type=Path, required=True)
    setup.add_argument("--model", required=True, help="Exact model ID exposed by the local server")
    setup.add_argument(
        "--artifact-sha256", required=True, help="Operator-verified model file digest",
    )
    setup.add_argument("--output", type=Path, required=True)
    setup.set_defaults(run=prepare)
    gen = sub.add_parser("generate", help="Query the served runtime and save answers")
    inputs = gen.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--queries", type=Path)
    inputs.add_argument("--study", type=Path, help="Directory created by prepare")
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--url", default="http://127.0.0.1:8000")
    gen.add_argument("--timeout", type=float, default=900)
    gen.set_defaults(run=generate)
    make = sub.add_parser("build", help="Build an immutable review pack")
    make.add_argument("--answers", type=Path, required=True)
    make.add_argument("--study", type=Path, help="Verify all answers against a prepared study")
    make.add_argument("--output", type=Path, required=True)
    make.set_defaults(run=build_pack)
    rec = sub.add_parser("record", help="Review unresolved cases interactively")
    rec.add_argument("--pack", type=Path, required=True)
    rec.add_argument("--reviewer", required=True)
    rec.set_defaults(run=record)
    total = sub.add_parser("summarize", help="Validate verdicts and write summary.json")
    total.add_argument("--pack", type=Path, required=True)
    total.set_defaults(run=summarize)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
