"""Probe whether VERA refuses in-domain questions and how it handles controls.

Runs the same pinned base model at LoRA scale 0 and 1 through the VERA
orchestrator, with bundled corpus snapshots, hash embeddings and no live
sources. Every query is classified as a domain question, an unrelated
request or social conversation, so over-refusal and scope leaks are visible.

This is a directional probe, not a benchmark: the sample is small, it uses a
single configuration and it does not measure factual accuracy.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "finetuning"))

from reproduce_step400 import (  # noqa: E402
    ADAPTER_FILE,
    ADAPTER_REPO,
    ADAPTER_REVISION,
    ADAPTER_SHA256,
    BASE_FILE,
    BASE_REPO,
    BASE_REVISION,
    BASE_SHA256,
    MODEL_ID,
    ensure_artifact,
    require_llama_server,
    wait_for_server,
)
from vera_finetuning.local_server import (  # noqa: E402
    adapter_id,
    model_id,
    set_adapter_scale,
)
from vera_finetuning.scope import CASES, settings_for  # noqa: E402

from vera.domain.reports import AnalysisResult  # noqa: E402
from vera.domain.requests import AnalysisRequest  # noqa: E402
from vera.workflow.orchestrator import VeraOrchestrator  # noqa: E402


def run(args: argparse.Namespace) -> dict:
    server_binary = require_llama_server(args.llama_server)
    artifact_dir = ROOT / ".vera/reproduce-step400"
    base = ensure_artifact(
        ROOT / ".vera/models/qwen3.5-4b-mtp" / BASE_FILE,
        artifact_dir / "base", BASE_REPO, BASE_REVISION, BASE_FILE, BASE_SHA256,
    )
    adapter = ensure_artifact(
        ROOT / ".vera/finetuning/adapter-step400" / ADAPTER_FILE,
        artifact_dir / "adapter", ADAPTER_REPO, ADAPTER_REVISION, ADAPTER_FILE, ADAPTER_SHA256,
    )
    url = f"http://127.0.0.1:{args.port}"
    command = [
        server_binary, "-m", str(base), "--lora", str(adapter),
        "-ngl", str(args.gpu_layers), "-fa", "on", "--ctx-size", "8192",
        "--parallel", "1", "--reasoning", "off", "--reasoning-budget", "0",
        "--host", "127.0.0.1", "--port", str(args.port), "--alias", MODEL_ID,
    ]
    cases = [case for case in CASES if not args.case or case["name"] in set(args.case)]
    if not cases:
        raise ValueError("No probe case matches --case")
    with tempfile.TemporaryDirectory(prefix="vera-scope-probe-") as directory:
        root = Path(directory)
        log_path = root / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_for_server(process, url, log_path, args.startup_timeout)
                with httpx.Client(base_url=url, timeout=args.request_timeout) as client:
                    model = model_id(client, MODEL_ID)
                    identifier, original = adapter_id(client, None)
                    rows = []
                    try:
                        for variant, scale in (("base", 0.0), ("adapter", 1.0)):
                            set_adapter_scale(client, identifier, scale)
                            variant_dir = root / variant
                            variant_dir.mkdir()
                            settings = settings_for(
                                model, url, variant_dir, args.backend,
                            )
                            with VeraOrchestrator(settings, review_enabled=False) as engine:
                                for case in cases:
                                    name, query, kind = case["name"], case["query"], case["kind"]
                                    result = engine.analyze(AnalysisRequest(
                                        query=query,
                                        session_id=f"{variant}-{name}-{uuid4().hex[:8]}",
                                    ))
                                    if not isinstance(result, AnalysisResult):
                                        raise RuntimeError(f"{variant}/{name}: no analysis")
                                    rows.append({
                                        "variant": variant,
                                        "case": name,
                                        "kind": kind,
                                        "query": query,
                                        "out_of_scope": result.metadata.get("out_of_scope"),
                                        "statuses": [c.status.value for c in result.claims],
                                        "citations": sum(len(c.citations) for c in result.claims),
                                        "validation_failures": (
                                            result.reflection.validation_failures
                                        ),
                                        "answer_preview": result.answer[:400],
                                    })
                    finally:
                        set_adapter_scale(client, identifier, original)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    summary = {}
    for variant in ("base", "adapter"):
        for kind in ("domain", "out", "social"):
            selected = [
                row for row in rows if row["variant"] == variant and row["kind"] == kind
            ]
            summary[f"{variant}_{kind}"] = {
                "n": len(selected),
                "out_of_scope": sum(bool(row["out_of_scope"]) for row in selected),
                "with_claims": sum(bool(row["statuses"]) for row in selected),
            }
    return {
        "model": model,
        "response_language": "English",
        "retrieval_k": 5,
        "embedding_backend": args.backend,
        "corpus": "bundled repository snapshots only",
        "react_enabled": False,
        "live_sources": False,
        "summary": summary,
        "results": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llama-server", default="llama-server")
    parser.add_argument("--port", type=int, default=1236)
    parser.add_argument("--gpu-layers", type=int, default=99)
    parser.add_argument("--startup-timeout", type=int, default=180)
    parser.add_argument("--request-timeout", type=float, default=180)
    parser.add_argument("--case", action="append", help="Run only this case name.")
    parser.add_argument(
        "--backend", choices=("hash", "sentence-transformers"), default="hash",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.gpu_layers < 0:
        parser.error("--port must be 1..65535 and --gpu-layers cannot be negative")
    if args.startup_timeout < 1 or args.request_timeout <= 0:
        parser.error("timeouts must be positive")
    if args.output and args.output.exists():
        parser.error("Choose a new report path; existing reports are never overwritten")
    report = run(args)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
