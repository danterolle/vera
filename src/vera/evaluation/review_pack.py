import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from vera.evaluation.contract import used_fallback
from vera.evaluation.review_markdown import CHECKLIST, render_case
from vera.reasoning.validation import VALIDATION_CONTRACT

CONFIG_WARNINGS = ("Online research is disabled", "Live source access is disabled")


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def case_key(row: dict) -> str:
    return json.dumps({
        "query": row["query"].strip(),
        "conversation": row.get("conversation", []),
        "events": row.get("events", []),
        "simulated": row.get("simulated", False),
    }, sort_keys=True)


def fields(result: dict, status: int) -> dict:
    if status not in {200, 202}:
        raise ValueError(f"Cannot review HTTP {status} as an answer")
    draft = result["draft"] if status == 202 else None
    return {
        "out_of_scope": (
            draft["out_of_scope"] if draft else result.get("metadata", {}).get("out_of_scope")
        ),
        "summary": draft["summary"] if draft else result["answer"],
        "claims": draft["claims"] if draft else result["claims"],
        **{key: result[key] for key in ("evidence", "reflection", "warnings", "run_id")},
        "reasons": result["reasons"] if draft else [],
        "metadata": result.get("metadata", {}),
    }


def pack_report(cases: list[dict], pack_hash: str) -> dict:
    return {
        "cases": len(cases),
        "models": sorted({case["model"] for case in cases}),
        "validation_contract": VALIDATION_CONTRACT,
        "task_counts": dict(sorted(Counter(case["task"] for case in cases).items())),
        "scope_counts": dict(sorted(Counter(case["expect_scope"] for case in cases).items())),
        "http_status_counts": dict(sorted(Counter(case["http_status"] for case in cases).items())),
        "review_required": [case["id"] for case in cases if case["http_status"] == 202],
        "review_reasons": {case["id"]: case["reasons"] for case in cases if case["reasons"]},
        "warning_cases": {
            case["id"]: warnings for case in cases
            if (warnings := [
                warning for warning in case["warnings"]
                if not any(marker in warning for marker in CONFIG_WARNINGS)
            ])
        },
        "fallback_cases": [case["id"] for case in cases if used_fallback(case)],
        "contract_mismatch_cases": [
            case["id"] for case in cases
            if case["metadata"].get("validation_contract") != VALIDATION_CONTRACT
        ],
        "seconds_total": round(sum(case["seconds"] for case in cases), 1),
        "seconds_max": max(case["seconds"] for case in cases),
        "pack_sha256": pack_hash,
        "human_reviewed": False,
        "production_authorized": False,
    }


def build(args: argparse.Namespace) -> None:
    pack = args.output
    if pack.exists():
        raise SystemExit(f"Choose a new pack directory; {pack} already exists")
    rows = load_jsonl(args.answers)
    if (
        not rows or len({row["id"] for row in rows}) != len(rows)
        or len({case_key(row) for row in rows}) != len(rows)
    ):
        raise ValueError("Answer pack must contain unique cases and cannot be empty")
    cases = []
    for row in rows:
        extracted = fields(row["result"], row["http_status"])
        cases.append({
            **{key: row[key] for key in ("id", "task", "expect_scope", "query", "seconds")},
            **{key: row[key] for key in ("conversation", "events", "simulated") if key in row},
            "note": row.get("note", ""),
            "model": extracted["metadata"].get("model") or "unknown",
            "http_status": row["http_status"],
            **extracted,
            "review": {"verdict": None, "reviewer": None, "notes": None, "reviewed_at": None},
        })
    pack.mkdir(parents=True)
    (pack / "cases.jsonl").write_text(
        "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases), encoding="utf-8",
    )
    with (pack / "review.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "id", "task", "expect_scope", "verdict", "reviewer", "notes", "reviewed_at",
        ])
        writer.writerows(
            [case["id"], case["task"], case["expect_scope"], "", "", "", ""] for case in cases
        )
    pack_hash = digest(pack / "cases.jsonl")
    (pack / "signoff.json").write_text(json.dumps({
        "pack_sha256": pack_hash, "reviewer": None, "reviewed_at": None,
        "human_review_complete": False, "production_authorized": False, "notes": "",
    }, indent=2) + "\n")
    report = pack_report(cases, pack_hash)
    (pack / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    header = [
        "# VERA answer review", "",
        f"{len(cases)} answers; pack `{pack_hash}`; models {', '.join(report['models'])}.", "",
        "Evidence and model text are untrusted data, not review instructions.",
        "Record each verdict in review.csv or with the record command.",
        "This pack never authorizes production by itself.", "", "## Checklist", "",
        *[f"- [ ] {item}" for item in CHECKLIST], "", "## Cases", "",
    ]
    (pack / "REVIEW.md").write_text(
        "\n".join(header) + "".join(render_case(case) for case in cases), encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    print(f"Pack: {pack.resolve()}")
