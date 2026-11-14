"""Generate and review runtime answers without training or authorizing deployment."""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from vera.evaluation.review_pack import build, case_key, load_jsonl
from vera.evaluation.review_verdicts import record, summarize


def generate(args: argparse.Namespace) -> None:
    queries = load_jsonl(args.queries)
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
            "query", "task", "expect_scope", "conversation", "events", "simulated",
        )):
            raise ValueError(f"{identifier}: cannot resume with different case inputs")
    output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=args.timeout) as client, output.open("a") as stream:
        for query in queries:
            if query["id"] in done:
                continue
            started = time.monotonic()
            response = client.post(
                args.url.rstrip("/") + "/v1/analyze",
                json={
                    "query": query["query"], "session_id": f"review-{query['id']}",
                    **{key: query[key] for key in ("conversation", "events", "simulated")
                       if key in query},
                },
            )
            seconds = round(time.monotonic() - started, 2)
            if response.status_code not in {200, 202}:
                raise SystemExit(
                    f"{query['id']}: HTTP {response.status_code}: {response.text[:300]}"
                )
            stream.write(json.dumps({
                **query, "http_status": response.status_code,
                "seconds": seconds, "result": response.json(),
            }, ensure_ascii=False) + "\n")
            stream.flush()
            print(f"{query['id']} {response.status_code} {seconds:.1f}s", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="Query the served runtime and save answers")
    gen.add_argument("--queries", type=Path, required=True)
    gen.add_argument("--output", type=Path, required=True)
    gen.add_argument("--url", default="http://127.0.0.1:8000")
    gen.add_argument("--timeout", type=float, default=900)
    gen.set_defaults(run=generate)
    make = sub.add_parser("build", help="Build an immutable review pack")
    make.add_argument("--answers", type=Path, required=True)
    make.add_argument("--output", type=Path, required=True)
    make.set_defaults(run=build)
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
