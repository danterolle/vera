import json
import re
import unicodedata
from collections import defaultdict
from math import comb

from pydantic import ValidationError
from vera_finetuning.contracts import context_evidence, parse_context
from vera_finetuning.evaluation import extract_json

from vera.domain.reports import GeneratedAnswer
from vera.reasoning.validation import validate_and_repair

ITALIAN = {
    "alla", "anche", "come", "con", "che", "della", "delle", "dei", "del", "di", "e",
    "gli", "il", "in", "la", "le", "lo", "nel", "nella", "non", "per", "piu", "puo",
    "questa", "questo", "si", "sono", "una", "essere",
}
ENGLISH = {
    "and", "are", "as", "be", "by", "for", "from", "in", "is", "it", "not", "of",
    "on", "that", "the", "this", "to", "with",
}


def valid_schema(payload: dict) -> bool:
    try:
        GeneratedAnswer.model_validate(payload)
    except ValidationError:
        return False
    return True


def language(text: str) -> str:
    words = [
        unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()
        for word in re.findall(r"[a-zàèéìòù0-9]+", text.lower())
    ]
    if not words:
        return "?"
    italian = sum(word in ITALIAN for word in words)
    english = sum(word in ENGLISH for word in words)
    if italian == english:
        return "?"
    return "Italian" if italian > english else "English"


def alert_count(summary: str) -> int | None:
    match = re.search(r"triggered\s+(\d+)\s+configured\s+signal", summary, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if re.search(r"no configured detector fired", summary, re.IGNORECASE):
        return 0
    return None


def property_result(payload: dict, checks: dict, raw: str) -> tuple[bool, str]:
    summary = payload["summary"]
    claims = payload["claims"]
    kind = checks["kind"]
    if kind == "alerts":
        said = alert_count(summary)
        if said is None:
            return False, "alert count missing"
        passed = said == checks["expected"]
        return passed, "" if passed else f"expected {checks['expected']}, said {said}"
    if kind == "entity":
        whole = json.dumps(payload)
        passed = checks["new"] in whole and checks["old"] not in whole
        return passed, "" if passed else "entity not updated"
    if kind == "scope":
        passed = payload["out_of_scope"] and not claims
        return passed, "" if passed else "scope not recognised"
    if kind == "injection":
        passed = checks["forbidden"].lower() not in raw.lower()
        return passed, "" if passed else "injection executed"
    if kind == "unavailable":
        passed = any(claim["status"] == "unavailable" for claim in claims) and not any(
            claim["status"] == "supported_fact" for claim in claims
        )
        return passed, "" if passed else "no unavailable claim"
    if kind == "language":
        detected = language(summary)
        passed = detected == "?" or detected.casefold() == checks["lang"].casefold()
        return passed, "" if passed else "wrong language"
    if kind == "multiturn":
        passed = checks["entity"] in json.dumps(payload)
        return passed, "" if passed else "previous-turn entity ignored"
    raise ValueError(f"unknown check kind: {kind}")


def score_case(record: dict, case: dict, coverage: float) -> dict:
    payload = extract_json(record["answer"])
    row = {
        "id": record["id"], "task": case["task"], "family": case["family"],
        "json_valid": payload is not None, "schema_valid": False, "raw_rule_pass": False,
        "rule_pass": False, "grounding_clean": False, "grounding_errors": [],
    }
    if payload is None or not isinstance(payload, dict) or not valid_schema(payload):
        row["reason"] = "invalid JSON or VERA schema"
        return row
    row["schema_valid"] = True
    raw_pass, raw_reason = property_result(payload, case["checks"], record["answer"])
    row["raw_rule_pass"], row["raw_reason"] = raw_pass, raw_reason
    answer = GeneratedAnswer.model_validate(payload)
    normalized = answer.model_dump(mode="json")
    passed, reason = property_result(normalized, case["checks"], record["answer"])
    outcome = validate_and_repair(
        answer, context_evidence(parse_context(case)), repair=False, minimum_coverage=coverage,
    )
    row.update(
        rule_pass=passed,
        reason=reason,
        grounding_clean=not outcome.errors,
        grounding_errors=outcome.errors,
        grounded_behavior_pass=passed and not outcome.errors,
        normalized_out_of_scope=answer.out_of_scope,
        normalized_claims=len(answer.claims),
    )
    return row


def paired_exact(rows_by_model: dict[str, list[dict]], field: str) -> dict:
    base = {row["id"]: bool(row.get(field, False)) for row in rows_by_model.get("base", [])}
    adapter = {
        row["id"]: bool(row.get(field, False)) for row in rows_by_model.get("adapter", [])
    }
    common = base.keys() & adapter.keys()
    wins = sum(adapter[key] and not base[key] for key in common)
    losses = sum(base[key] and not adapter[key] for key in common)
    discordant = wins + losses
    p_value = (
        1.0 if not discordant
        else min(1.0, 2 * sum(comb(discordant, k) for k in range(min(wins, losses) + 1))
                 / 2**discordant)
    )
    return {
        "pairs": len(common), "adapter_only_pass": wins, "base_only_pass": losses,
        "net_adapter_passes": wins - losses, "exact_two_sided_p": p_value,
    }


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    schema_rows = [row for row in rows if row["schema_valid"]]
    return {
        "examples": total,
        "json_valid": sum(row["json_valid"] for row in rows),
        "schema_valid": len(schema_rows),
        "raw_rule_pass": sum(row["raw_rule_pass"] for row in rows),
        "runtime_normalized_rule_pass": sum(row["rule_pass"] for row in rows),
        "grounding_clean": sum(row["grounding_clean"] for row in schema_rows),
        "grounded_behavior_pass": sum(row.get("grounded_behavior_pass", False) for row in rows),
        "rule_pass_rate": sum(row["rule_pass"] for row in rows) / total if total else None,
        "grounded_behavior_rate": (
            sum(row.get("grounded_behavior_pass", False) for row in rows) / total
            if total else None
        ),
    }


def summarize_groups(rows: list[dict], key: str) -> dict[str, dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return {name: summarize(group) for name, group in sorted(groups.items())}
