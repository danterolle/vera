"""Generate, review and summarize a human answer pack for the served VERA runtime.

The pack is evidence for a human decision, not an automatic promotion gate. It never
trains, tunes or selects a model: it only records what the runtime answered and what a
person decided after reading the supplied evidence.
"""

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

VERDICTS = {"accept", "fix", "reject"}
CHECKLIST = (
    "Every supported_fact is supported by the evidence it cites.",
    "Every quotation is verbatim in the cited evidence.",
    "The summary does not assert local compromise, exposure or deployment.",
    "Scope and conversational intent match the request.",
    "Abstentions name what is missing instead of substituting an unrelated record.",
    "The answer language matches the question.",
)
CONFIG_WARNINGS = ("Online research is disabled", "Live source access is disabled")


def notable_warnings(warnings: list[str]) -> list[str]:
    """Keep warnings that are not the expected local configuration."""
    return [
        warning for warning in warnings
        if not any(marker in warning for marker in CONFIG_WARNINGS)
    ]


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fields(result: dict, status: int) -> dict:
    if status == 202:
        draft = result["draft"]
        return {
            "out_of_scope": draft["out_of_scope"],
            "summary": draft["summary"],
            "claims": draft["claims"],
            "evidence": result["evidence"],
            "reflection": result["reflection"],
            "warnings": result["warnings"],
            "reasons": result["reasons"],
            "metadata": result.get("metadata", {}),
            "run_id": result["run_id"],
        }
    return {
        "out_of_scope": result.get("metadata", {}).get("out_of_scope"),
        "summary": result["answer"],
        "claims": result["claims"],
        "evidence": result["evidence"],
        "reflection": result["reflection"],
        "warnings": result["warnings"],
        "reasons": [],
        "metadata": result.get("metadata", {}),
        "run_id": result["run_id"],
    }


def generate(args: argparse.Namespace) -> None:
    queries = load_jsonl(args.queries)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    done = {row["id"] for row in load_jsonl(output)}
    with httpx.Client(timeout=args.timeout) as client, output.open("a") as stream:
        for query in queries:
            if query["id"] in done:
                continue
            started = time.monotonic()
            response = client.post(
                args.url.rstrip("/") + "/v1/analyze",
                json={"query": query["query"], "session_id": f"review-{query['id']}"},
            )
            seconds = round(time.monotonic() - started, 2)
            if response.status_code not in {200, 202}:
                raise SystemExit(
                    f"{query['id']}: HTTP {response.status_code}: {response.text[:300]}"
                )
            stream.write(
                json.dumps(
                    {
                        **query,
                        "http_status": response.status_code,
                        "seconds": seconds,
                        "result": response.json(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            stream.flush()
            print(
                f"{query['id']} {response.status_code} {seconds:.1f}s",
                file=sys.stderr,
            )


def cell(text: str, limit: int = 700) -> str:
    collapsed = " ".join(str(text).split()).replace("|", "\\|")
    return collapsed[:limit] + ("…" if len(collapsed) > limit else "")


def render_case(case: dict) -> str:
    lines = [
        f"### {case['id']} · {case['task']} · expected scope: {case['expect_scope']}",
        "",
        f"**Question:** {case['query']}",
        "",
        f"**Snapshot/model:** `{case['model']}` · {case['http_status']} · "
        f"{case['seconds']}s · run `{case['run_id']}`",
        "",
        f"**Summary:** {cell(case['summary'])}",
        "",
        "| Status | Claim | Quotes |",
        "| --- | --- | --- |",
    ]
    by_id = {item["id"]: item for item in case["evidence"]}
    for claim in case["claims"]:
        quotes = "; ".join(
            f"“{cell(citation.get('supporting_quote', ''), 160)}” "
            f"({citation.get('evidence_id', '?')})"
            for citation in claim.get("citations", [])
        ) or "—"
        lines.append(
            f"| {claim['status']} | {cell(claim['text'], 300)} | {quotes} |"
        )
    if not case["claims"]:
        lines.append("| — | No claims. | — |")
    lines.extend(["", "**Supplied evidence**", ""])
    for identifier, item in by_id.items():
        lines.append(
            f"- `{identifier}` · {item.get('source', '')} · {item.get('status', '')} · "
            f"{cell(item.get('title', ''), 200)}: {cell(item.get('content', ''))}"
        )
    if not by_id:
        lines.append("- None supplied.")
    reflection = case["reflection"]
    lines.extend([
        "",
        f"**Reflection:** unsupported={reflection.get('unsupported_claims')} · "
        f"validation={reflection.get('validation_failures')} · "
        f"missing={', '.join(reflection.get('missing_sources', [])) or 'none'}",
        "",
        f"**Warnings:** {'; '.join(case['warnings']) or 'none'}",
        f"**Review reasons:** {'; '.join(case['reasons']) or 'none'}",
        "",
        "**Verdict:** ☐ accept · ☐ fix · ☐ reject  ",
        "**Notes:**",
        "",
    ])
    return "\n".join(lines) + "\n"


def build(args: argparse.Namespace) -> None:
    pack = Path(args.output)
    if pack.exists():
        raise SystemExit(f"Choose a new pack directory; {pack} already exists")
    rows = load_jsonl(args.answers)
    if not rows:
        raise SystemExit(f"No answers in {args.answers}")
    cases = []
    for row in rows:
        extracted = fields(row["result"], row["http_status"])
        cases.append({
            "id": row["id"],
            "task": row["task"],
            "expect_scope": row["expect_scope"],
            "note": row.get("note", ""),
            "query": row["query"],
            "model": extracted["metadata"].get("model") or "unknown",
            "http_status": row["http_status"],
            "seconds": row["seconds"],
            "run_id": extracted["run_id"],
            **{key: extracted[key] for key in (
                "out_of_scope", "summary", "claims", "evidence", "reflection",
                "warnings", "reasons", "metadata",
            )},
            "review": {
                "verdict": None, "reviewer": None, "notes": None, "reviewed_at": None,
            },
        })
    pack.mkdir(parents=True)
    write_jsonl(pack / "cases.jsonl", cases)
    with (pack / "review.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["id", "task", "expect_scope", "verdict", "reviewer", "notes", "reviewed_at"]
        )
        for case in cases:
            writer.writerow(
                [case["id"], case["task"], case["expect_scope"], "", "", "", ""]
            )
    (pack / "signoff.json").write_text(json.dumps({
        "pack_sha256": digest(pack / "cases.jsonl"),
        "reviewer": None,
        "reviewed_at": None,
        "human_review_complete": False,
        "production_authorized": False,
        "notes": "",
    }, indent=2) + "\n")
    report = {
        "cases": len(cases),
        "models": sorted({case["model"] for case in cases}),
        "task_counts": dict(sorted(Counter(case["task"] for case in cases).items())),
        "scope_counts": dict(
            sorted(Counter(case["expect_scope"] for case in cases).items())
        ),
        "http_status_counts": dict(
            sorted(Counter(case["http_status"] for case in cases).items())
        ),
        "review_required": [
            case["id"] for case in cases if case["http_status"] == 202
        ],
        "review_reasons": {
            case["id"]: case["reasons"] for case in cases if case["reasons"]
        },
        "warning_cases": {
            case["id"]: notable_warnings(case["warnings"])
            for case in cases
            if notable_warnings(case["warnings"])
        },
        "seconds_total": round(sum(case["seconds"] for case in cases), 1),
        "seconds_max": max(case["seconds"] for case in cases),
        "pack_sha256": digest(pack / "cases.jsonl"),
        "human_reviewed": False,
    }
    (pack / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    header = [
        "# VERA v4 answer review",
        "",
        f"{len(cases)} answers · pack `{report['pack_sha256'][:16]}…` · "
        f"models {', '.join(report['models'])}",
        "",
        "A case counts only after a person sets a verdict in `review.csv` (or with "
        "`--record`). This pack does not authorize production by itself.",
        "",
        "## Checklist",
        "",
        *[f"- [ ] {item}" for item in CHECKLIST],
        "",
        "## Cases",
        "",
    ]
    (pack / "REVIEW.md").write_text(
        "\n".join(header) + "".join(render_case(case) for case in cases),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    print(f"Pack: {pack.resolve()}")


def read_review(pack: Path) -> tuple[list[dict], list[dict]]:
    with (pack / "review.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    return load_jsonl(pack / "cases.jsonl"), rows


def record(args: argparse.Namespace) -> None:
    pack = Path(args.pack)
    cases, rows = read_review(pack)
    by_id = {case["id"]: case for case in cases}
    with (pack / "review.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            if row["verdict"] in VERDICTS:
                writer.writerow(row)
                continue
            print("\n" + "=" * 78)
            print(render_case(by_id[row["id"]]))
            answer = input("Verdict [a]ccept / [f]ix / [r]eject / [s]kip: ").strip().lower()
            if answer == "s":
                writer.writerow(row)
                continue
            verdict = {"a": "accept", "f": "fix", "r": "reject"}.get(answer)
            if verdict is None:
                print("Unrecognized verdict; row left unresolved.", file=sys.stderr)
                writer.writerow(row)
                continue
            notes = input("Notes (required for fix/reject): ").strip()
            if verdict in {"fix", "reject"} and not notes:
                print("Notes are required; row left unresolved.", file=sys.stderr)
                writer.writerow(row)
                continue
            row.update({
                "verdict": verdict,
                "reviewer": args.reviewer,
                "notes": notes or None,
                "reviewed_at": datetime.now(UTC).date().isoformat(),
            })
            writer.writerow(row)
            stream.flush()
    summarize(args)


def summarize(args: argparse.Namespace) -> None:
    pack = Path(args.pack)
    cases, rows = read_review(pack)
    signoff = json.loads((pack / "signoff.json").read_text())
    verdicts = Counter(row["verdict"] for row in rows if row["verdict"] in VERDICTS)
    unresolved = [row["id"] for row in rows if row["verdict"] not in VERDICTS]
    missing_notes = [
        row["id"] for row in rows
        if row["verdict"] in {"fix", "reject"} and not (row.get("notes") or "").strip()
    ]
    current_hash = digest(pack / "cases.jsonl")
    ready = (
        bool(signoff.get("reviewer"))
        and bool(signoff.get("reviewed_at"))
        and signoff.get("human_review_complete") is True
        and not unresolved
        and not missing_notes
        and verdicts["accept"] == len(rows)
        and signoff.get("pack_sha256") == current_hash
    )
    summary = {
        "cases": len(rows),
        "verdicts": dict(sorted(verdicts.items())),
        "unresolved": unresolved,
        "missing_notes": missing_notes,
        "reviewer": signoff.get("reviewer"),
        "reviewed_at": signoff.get("reviewed_at"),
        "pack_sha256": current_hash,
        "hash_matches_signoff": signoff.get("pack_sha256") == current_hash,
        "human_review_complete": ready,
        "production_authorized": False,
    }
    (pack / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


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
