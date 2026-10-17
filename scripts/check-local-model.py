"""Exercise local Qwen, graph citations, unavailable knowledge, and domain scope."""

import json
import time
from pathlib import Path
from uuid import uuid4

import httpx

CASES = [
    ("powershell", "Explain PowerShell. Give a brief answer with one sourced claim.", "graph"),
    ("weakness", "Explain CWE-89. Give a brief answer with one sourced claim.", "graph"),
    ("missing", "Analyze CVE-2099-99999. State explicitly if evidence is missing.", "missing"),
    ("scope", "Qual è la ricetta della carbonara?", "scope"),
]


def check(result: dict, expectation: str) -> bool:
    metadata = result["metadata"]
    if metadata.get("provider_fallback") or metadata.get("model") != "vera-qwen3.5-4b":
        return False
    claims = result["claims"]
    if expectation == "graph":
        graph = metadata["knowledge_graph"]
        return bool(
            graph.get("attempted") and graph.get("available")
            and graph.get("cited_evidence_ids")
            and any(claim["status"] == "supported_fact" for claim in claims)
            and result["reflection"]["factual_validation_failures"] == 0
        )
    if expectation == "missing":
        answer = result["answer"].lower()
        missing = any(term in answer for term in [
            "unavailable", "not contain", "no evidence", "missing", "insufficient",
            "not provided", "not include", "non disponibil", "manc", "non risult",
        ]) or any(claim["status"] == "unavailable" for claim in claims)
        return missing and not any(claim["status"] == "supported_fact" for claim in claims)
    answer = result["answer"].lower()
    return not claims and any(
        term in answer for term in ["cybersecurity", "sicurezza", "informatic"]
    )


def main() -> None:
    reports = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=260) as client:
        for name, query, expectation in CASES:
            started = time.monotonic()
            response = client.post(
                "/v1/analyze", json={
                    "query": query, "session_id": f"local-qwen35-check-{name}-{uuid4().hex[:8]}",
                },
            )
            response.raise_for_status()
            result = response.json()
            passed = check(result, expectation)
            report = {
                "case": name, "passed": passed, "seconds": round(time.monotonic() - started, 2),
                "result": result,
            }
            reports.append(report)
            print(json.dumps({
                "case": name, "passed": passed, "seconds": report["seconds"],
                "run_id": result["run_id"],
                "kg_citations": result["metadata"]["knowledge_graph"].get("cited_evidence_ids"),
                "fallback": result["metadata"].get("provider_fallback"),
            }), flush=True)
    output = Path(".vera/local-model-checks.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(reports, indent=2, ensure_ascii=False) + "\n")
    if not all(item["passed"] for item in reports):
        raise SystemExit("Some local-model checks failed; inspect .vera/local-model-checks.json")


if __name__ == "__main__":
    main()
