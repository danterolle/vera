"""Compare the local base model and loaded LoRA through VERA's runtime."""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import httpx
from vera_finetuning.local_server import (
    adapter_id,
    local_server_url,
    model_id,
    set_adapter_scale,
)

from vera.config import Settings
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.providers.prompts import SYSTEM_PROMPT
from vera.workflow.orchestrator import VeraOrchestrator

CASES = (
    ("powershell", "Explain PowerShell. Give a brief answer with one sourced claim.", "sourced"),
    ("weakness", "Explain CWE-89. Give a brief answer with one sourced claim.", "sourced"),
    ("missing", "Analyze CVE-2099-99999. State explicitly if evidence is missing.", "missing"),
    ("scope", "What is the recipe for carbonara?", "scope"),
)


def passes(result: AnalysisResult, expectation: str) -> bool:
    statuses = {claim.status.value for claim in result.claims}
    if (
        result.metadata.get("provider_fallback")
        or result.reflection.validation_failures
        or result.reflection.factual_validation_failures
    ):
        return False
    if expectation == "sourced":
        return (
            not result.metadata.get("out_of_scope")
            and "supported_fact" in statuses
            and any(claim.citations for claim in result.claims)
        )
    if expectation == "missing":
        text = result.answer.casefold()
        explicit = any(
            term in text for term in ("unavailable", "no evidence", "missing", "insufficient")
        )
        return (
            not result.metadata.get("out_of_scope")
            and "supported_fact" not in statuses
            and ("unavailable" in statuses or explicit)
        )
    return bool(result.metadata.get("out_of_scope")) and not result.claims


def result_row(
    result: AnalysisResult, variant: str, case: str, expectation: str
) -> dict:
    return {
        "variant": variant,
        "case": case,
        "passed": passes(result, expectation),
        "provider_fallback": result.metadata.get("provider_fallback"),
        "out_of_scope": result.metadata.get("out_of_scope"),
        "claim_statuses": [claim.status.value for claim in result.claims],
        "citations": sum(len(claim.citations) for claim in result.claims),
        "validation_failures": result.reflection.validation_failures,
        "factual_validation_failures": result.reflection.factual_validation_failures,
        "answer_preview": result.answer[:420],
    }


def run(args: argparse.Namespace) -> dict:
    server = local_server_url(args.server_url)
    with httpx.Client(base_url=server, timeout=args.timeout) as client:
        model = model_id(client, args.model)
        identifier, original_scale = adapter_id(client, args.adapter_id)
        try:
            rows = []
            with TemporaryDirectory(prefix="vera-local-adapter-") as directory:
                settings = Settings(_env_file=None).model_copy(update={
                    "llm_provider": "openai",
                    "llm_model": model,
                    "llm_base_url": f"{server}/v1",
                    "llm_api_key": None,
                    "llm_response_format": "json_schema",
                    "llm_reasoning_effort": None,
                    "llm_timeout_seconds": 300,
                    "llm_max_output_tokens": 4096,
                    "max_model_calls": 4,
                    "live_sources": False,
                    "web_search_enabled": False,
                    "kg_enabled": False,
                    "react_enabled": False,
                    "memory_k": 0,
                    "response_language": "English",
                    "embedding_backend": "hash",
                    "retrieval_k": 5,
                    "retrieval_min_score": 0.05,
                    "grounding_min_coverage": 0.55,
                })
                for variant, scale in (("base", 0.0), ("adapter", 1.0)):
                    set_adapter_scale(client, identifier, scale)
                    selected = settings.model_copy(update={
                        "db_path": Path(directory) / f"{variant}.db",
                        "corpus_dir": Path(directory) / f"{variant}-corpus",
                    })
                    with VeraOrchestrator(selected, review_enabled=False) as engine:
                        for name, query, expectation in CASES:
                            result = engine.analyze(AnalysisRequest(
                                query=query,
                                session_id=f"{variant}-{name}-{uuid4().hex[:8]}",
                            ))
                            if not isinstance(result, AnalysisResult):
                                raise RuntimeError(f"{variant}/{name} did not return an analysis")
                            rows.append(result_row(result, variant, name, expectation))
        finally:
            set_adapter_scale(client, identifier, original_scale)
    summary = {
        variant: sum(row["passed"] for row in rows if row["variant"] == variant)
        for variant in ("base", "adapter")
    }
    return {
        "model": model,
        "adapter_id": identifier,
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "cases_per_variant": len(CASES),
        "response_language": "English",
        "max_output_tokens": 4096,
        "retrieval_k": 5,
        "corpus": "bundled repository snapshots only",
        "react_enabled": False,
        "live_sources": False,
        "database": "temporary",
        "summary": summary,
        "results": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", default="http://127.0.0.1:1234")
    parser.add_argument("--model", help="Exact ID from the local server's /v1/models.")
    parser.add_argument("--adapter-id", type=int)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.output and args.output.exists():
        parser.error("Choose a new output file; existing reports are never overwritten")
    report = run(args)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
