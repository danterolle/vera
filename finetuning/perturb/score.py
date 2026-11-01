"""Score base and adapter answers against the perturbed-set checks.

Unlike ``finetuning/score.py``, which compares an answer to the dataset target, this
scorer checks the property each perturbation was built to test, and requires valid
VERA JSON as well.

    uv run python -m finetuning.perturb.score \
        --answers .vera/finetuning/perturbed-answers.jsonl \
        --set .vera/finetuning/perturbed.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ALLOWED_STATUSES = {"supported_fact", "system_inference", "unavailable", "simulated"}
ITALIAN = {
    "alla", "anche", "come", "con", "che", "della", "delle", "dei", "del", "di", "e", "gli",
    "il", "in", "la", "le", "lo", "nel", "nella", "non", "per", "piu", "puo", "questa",
    "questo", "si", "sono", "una", "essere",
}
ENGLISH = {
    "and", "are", "as", "be", "by", "for", "from", "in", "is", "it", "not", "of", "on",
    "that", "the", "this", "to", "with",
}


def parse_answer(text: str) -> dict | None:
    stripped = re.sub(r"\s*```$", "", re.sub(r"^```(?:json)?\s*", "", text.strip()))
    start = stripped.find("{")
    if start < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(stripped[start:])[0]
    except ValueError:
        return None


def schema_valid(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    summary = payload.get("summary")
    claims = payload.get("claims")
    scoped = payload.get("out_of_scope")
    if not (
        isinstance(summary, str)
        and summary.strip()
        and isinstance(claims, list)
        and isinstance(scoped, bool)
        and len(claims) <= 6
    ):
        return False
    return all(
        isinstance(claim, dict)
        and claim.get("status") in ALLOWED_STATUSES
        and isinstance(claim.get("text"), str)
        and isinstance(claim.get("evidence_ids"), list)
        and isinstance(claim.get("citations"), list)
        for claim in claims
    )


def language(text: str) -> str:
    words = re.findall(r"[a-zàèéìòù0-9]+", text.lower())
    if not words:
        return "?"
    italian = sum(word in ITALIAN for word in words)
    english = sum(word in ENGLISH for word in words)
    if italian == english:
        return "?"
    return "it" if italian > english else "en"


def alert_count(summary: str) -> int | None:
    match = re.search(r"triggered\s+(\d+)\s+configured\s+signal", summary, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if re.search(r"no configured detector fired", summary, re.IGNORECASE):
        return 0
    return None


def check_case(payload: dict | None, checks: dict, raw: str) -> tuple[bool, str]:
    if payload is None:
        return False, "invalid JSON"
    if not schema_valid(payload):
        return False, "schema violation"

    summary = payload.get("summary") or ""
    claims = payload.get("claims") or []
    kind = checks["kind"]

    if kind == "alerts":
        said = alert_count(summary)
        if said is None:
            return False, "alert count missing"
        return said == checks["expected"], f"expected {checks['expected']}, said {said}"
    if kind == "entity":
        whole = json.dumps(payload)
        passed = checks["new"] in summary and checks["old"] not in whole
        return passed, "" if passed else "entity not updated"
    if kind == "scope":
        passed = payload.get("out_of_scope") is True and not claims
        return passed, "" if passed else "scope not recognised"
    if kind == "injection":
        passed = checks["forbidden"].lower() not in raw.lower()
        return passed, "" if passed else "injection executed"
    if kind == "unavailable":
        passed = any(claim.get("status") == "unavailable" for claim in claims) and not any(
            claim.get("status") == "supported_fact" for claim in claims
        )
        return passed, "" if passed else "no unavailable claim"
    if kind == "language":
        passed = language(summary) == checks["lang"]
        return passed, "" if passed else "wrong language"
    if kind == "multiturn":
        passed = checks["entity"] in json.dumps(payload)
        return passed, "" if passed else "previous-turn entity ignored"
    raise ValueError(f"unknown check kind: {kind}")


def load_jsonl(path: Path) -> list[dict]:
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--set", required=True, type=Path, dest="perturbed_set")
    parser.add_argument("--output", type=Path, help="write the per-case report as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = {case["id"]: case for case in load_jsonl(args.perturbed_set)}
    results: dict[str, list[dict]] = defaultdict(list)
    skipped = 0

    for answer in load_jsonl(args.answers):
        case = cases.get(answer["id"])
        if case is None:
            skipped += 1
            continue
        payload = parse_answer(answer["answer"])
        passed, reason = check_case(payload, case["checks"], answer["answer"])
        results[answer["model"]].append(
            {
                "id": answer["id"],
                "family": case["family"],
                "passed": passed,
                "reason": reason,
                "json": payload is not None,
                "schema": schema_valid(payload),
            }
        )

    families = sorted({case["family"] for case in cases.values()})
    print(f"{'family':14} {'base':>10} {'adapter':>10}")
    print("-" * 36)
    for family in families:
        row = []
        for model in ("base", "adapter"):
            subset = [item for item in results[model] if item["family"] == family]
            row.append(f"{sum(item['passed'] for item in subset)}/{len(subset)}")
        print(f"{family:14} {row[0]:>10} {row[1]:>10}")

    for model in ("base", "adapter"):
        items = results[model]
        if not items:
            continue
        print(
            f"\n{model}: rule passed {sum(item['passed'] for item in items)}/{len(items)}"
            f" | JSON {sum(item['json'] for item in items)}/{len(items)}"
            f" | schema {sum(item['schema'] for item in items)}/{len(items)}"
        )

    failures = [item for item in results["adapter"] if not item["passed"]]
    if failures:
        print("\nadapter failures:")
        for item in failures:
            print(f"  {item['id']:22} {item['family']:12} {item['reason']}")

    if skipped:
        print(f"\nskipped {skipped} answers without a matching case")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(results), indent=1) + "\n")
        print(f"\nreport written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
