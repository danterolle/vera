import json
from datetime import date

from vera.domain.reports import GeneratedAnswer


def named_review(row: dict) -> bool:
    if not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip():
        return False
    try:
        date.fromisoformat(row.get("reviewed_at") or "")
    except (TypeError, ValueError):
        return False
    return True


def strict_answer(payload: dict) -> GeneratedAnswer:
    if set(payload) != {"summary", "claims", "out_of_scope"}:
        raise ValueError("Answer must contain exactly summary, claims and out_of_scope")
    claims = payload["claims"]
    if not isinstance(claims, list) or len(claims) > 6:
        raise ValueError("Answer must contain a list of at most six claims")
    if payload["out_of_scope"] is True and claims:
        raise ValueError("Out-of-scope answers cannot contain claims before normalization")
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {
            "text", "status", "evidence_ids", "citations",
        }:
            raise ValueError("Every claim must include text, status, evidence_ids and citations")
    return GeneratedAnswer.model_validate_json(json.dumps(payload), strict=True)


def used_fallback(row: dict) -> bool:
    result = row.get("result") or {}
    metadata = row.get("metadata") or result.get("metadata") or {}
    warnings = row.get("warnings") or result.get("warnings") or []
    return (
        row.get("provider_fallback") is True
        or metadata.get("provider_fallback") is True
        or metadata.get("provider") == "deterministic"
        or any("deterministic output used" in warning for warning in warnings)
    )
