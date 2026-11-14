import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from vera.evaluation.review_markdown import render_case
from vera.evaluation.review_pack import case_key, digest, load_jsonl, pack_report

VERDICTS = {"accept", "fix", "reject"}


def named_review(row: dict) -> bool:
    if not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip():
        return False
    try:
        date.fromisoformat(row.get("reviewed_at") or "")
    except (ValueError, TypeError):
        return False
    return True


def read_review(pack: Path) -> tuple[list[dict], list[dict]]:
    cases = load_jsonl(pack / "cases.jsonl")
    with (pack / "review.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    case_ids, row_ids = [case["id"] for case in cases], [row["id"] for row in rows]
    if (
        not cases or len(case_ids) != len(set(case_ids)) or len(row_ids) != len(set(row_ids))
        or set(row_ids) != set(case_ids)
        or len({case_key(case) for case in cases}) != len(cases)
    ):
        raise ValueError("review.csv must contain exactly one row per unique case")
    return cases, rows


def save_rows(pack: Path, rows: list[dict]) -> None:
    with NamedTemporaryFile(
        mode="w", dir=pack, newline="", encoding="utf-8", delete=False,
    ) as stream:
        temporary = Path(stream.name)
        try:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            temporary.replace(pack / "review.csv")
        finally:
            temporary.unlink(missing_ok=True)


def record(args: argparse.Namespace) -> None:
    pack = args.pack
    if not args.reviewer.strip():
        raise ValueError("A named human reviewer is required")
    cases, rows = read_review(pack)
    by_id = {case["id"]: case for case in cases}
    for row in rows:
        if (
            row["verdict"] in VERDICTS and named_review(row)
            and (row["verdict"] == "accept" or (row.get("notes") or "").strip())
        ):
            continue
        print("\n" + "=" * 78 + "\n" + render_case(by_id[row["id"]]))
        answer = input("Verdict [a]ccept / [f]ix / [r]eject / [s]kip: ").strip().lower()
        if answer == "s":
            continue
        verdict = {"a": "accept", "f": "fix", "r": "reject"}.get(answer)
        if verdict is None:
            print("Unrecognized verdict; row left unresolved.", file=sys.stderr)
            continue
        notes = input("Notes (required for fix/reject): ").strip()
        if verdict in {"fix", "reject"} and not notes:
            print("Notes are required; row left unresolved.", file=sys.stderr)
            continue
        row.update(
            verdict=verdict, reviewer=args.reviewer.strip(), notes=notes,
            reviewed_at=datetime.now(UTC).date().isoformat(),
        )
        save_rows(pack, rows)
    summarize(args)


def summarize(args: argparse.Namespace) -> None:
    pack = args.pack
    cases, rows = read_review(pack)
    signoff = json.loads((pack / "signoff.json").read_text())
    verdicts = Counter(row["verdict"] for row in rows if row["verdict"] in VERDICTS)
    unresolved = [row["id"] for row in rows if row["verdict"] not in VERDICTS]
    missing_notes = [
        row["id"] for row in rows
        if row["verdict"] in {"fix", "reject"} and not (row.get("notes") or "").strip()
    ]
    missing_reviewers = [row["id"] for row in rows if not named_review(row)]
    current_hash = digest(pack / "cases.jsonl")
    ready = (
        named_review(signoff) and signoff.get("human_review_complete") is True
        and not unresolved and not missing_notes and not missing_reviewers
        and verdicts["accept"] == len(rows) and signoff.get("pack_sha256") == current_hash
    )
    report = pack_report(cases, current_hash)
    models = report["models"]
    summary = {
        **{key: report[key] for key in ("cases", "fallback_cases", "contract_mismatch_cases")},
        "verdicts": dict(sorted(verdicts.items())),
        "unresolved": unresolved, "missing_notes": missing_notes,
        "missing_reviewers": missing_reviewers,
        "reviewer": signoff.get("reviewer"), "reviewed_at": signoff.get("reviewed_at"),
        "pack_sha256": current_hash,
        "hash_matches_signoff": signoff.get("pack_sha256") == current_hash,
        "human_review_complete": ready,
        "ready_for_authorization": (
            ready and len(cases) >= 40 and len(models) == 1 and models[0] != "unknown"
            and not report["fallback_cases"] and not report["contract_mismatch_cases"]
        ),
        "production_authorized": False,
    }
    (pack / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
