"""Exercise the configured local model, graph citations, missing data, and domain scope."""

import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

from vera.config import Settings

CASES = [
    ("powershell", "Explain PowerShell. Give a brief answer with one sourced claim.", "graph"),
    ("weakness", "Explain CWE-89. Give a brief answer with one sourced claim.", "graph"),
    ("missing", "Analyze CVE-2099-99999. State explicitly if evidence is missing.", "missing"),
    ("scope", "Qual è la ricetta della carbonara?", "scope"),
]


def check(result: dict, expectation: str, expected_model: str) -> bool:
    if "status" in result:
        return False
    metadata = result["metadata"]
    if metadata.get("provider_fallback") or metadata.get("model") != expected_model:
        return False
    claims = result["claims"]
    if expectation == "graph":
        if metadata.get("out_of_scope"):
            return False
        graph = metadata["knowledge_graph"]
        return bool(
            graph.get("attempted") and graph.get("available")
            and graph.get("cited_evidence_ids")
            and any(claim["status"] == "supported_fact" for claim in claims)
            and result["reflection"]["factual_validation_failures"] == 0
        )
    if expectation == "missing":
        if metadata.get("out_of_scope"):
            return False
        assessment = result["answer"].split("\n\n## ", 1)[0].lower()
        missing = any(term in assessment for term in [
            "unavailable", "not contain", "no evidence", "missing", "insufficient",
            "not provided", "not include", "non disponibil", "manc", "non risult",
        ]) or any(claim["status"] == "unavailable" for claim in claims)
        return missing and not any(claim["status"] == "supported_fact" for claim in claims)
    answer = result["answer"].lower()
    return bool(metadata.get("out_of_scope")) and not claims and any(
        term in answer for term in ["cybersecurity", "sicurezza", "informatic"]
    )


def summarize(result: dict, http_status: int, expectation: str, model: str) -> dict:
    if http_status == 202:
        if (
            result.get("status") != "pending"
            or not isinstance(result.get("run_id"), str)
            or not isinstance(result.get("reasons"), list)
        ):
            raise ValueError("HTTP 202 must contain a pending review with a run ID and reasons")
        return {
            "passed": False,
            "http_status": http_status,
            "status": "pending",
            "human_review_required": True,
            "run_id": result["run_id"],
            "reasons": result["reasons"],
            "kg_citations": None,
            "fallback": None,
        }
    if http_status != 200 or "status" in result:
        raise ValueError(f"Unexpected analysis response for HTTP {http_status}")
    metadata = result["metadata"]
    return {
        "passed": check(result, expectation, model),
        "http_status": http_status,
        "status": "completed",
        "human_review_required": False,
        "run_id": result["run_id"],
        "reasons": [],
        "kg_citations": metadata["knowledge_graph"].get("cited_evidence_ids"),
        "fallback": metadata.get("provider_fallback"),
    }


def main() -> None:
    settings = Settings()
    if settings.llm_provider == "deterministic":
        raise SystemExit("Configure an external VERA_LLM_PROVIDER before checking a local model")
    reports = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=260) as client:
        for name, query, expectation in CASES:
            started = time.monotonic()
            response = client.post(
                "/v1/analyze", json={
                    "query": query, "session_id": f"local-model-check-{name}-{uuid4().hex[:8]}",
                },
            )
            response.raise_for_status()
            result = response.json()
            summary = summarize(result, response.status_code, expectation, settings.llm_model)
            report = {
                "case": name,
                "seconds": round(time.monotonic() - started, 2),
                "result": result,
                **summary,
            }
            reports.append(report)
            display = {key: value for key, value in report.items() if key != "result"}
            print(json.dumps(display), flush=True)
    output = Path(".vera/local-model-checks.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(reports, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "passed": sum(item["passed"] for item in reports),
        "total": len(reports),
        "pending_reviews": sum(item["human_review_required"] for item in reports),
    }), flush=True)
    if not all(item["passed"] for item in reports):
        pending = [item["run_id"] for item in reports if item["human_review_required"]]
        detail = (
            f" Human review required for {', '.join(pending)}; open /chat."
            if pending else ""
        )
        raise SystemExit(
            f"Some local-model checks failed; inspect .vera/local-model-checks.json.{detail}"
        )


if __name__ == "__main__":
    main()
