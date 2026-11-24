"""Collect paired, offline retrieval observations for the VERA presentation."""

import json
import os
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from uuid import uuid4

from vera.config import Settings
from vera.data import resource
from vera.domain.enums import ClaimStatus, EvidenceStatus, SourceType
from vera.domain.evidence import Evidence
from vera.domain.reports import AnalysisResult
from vera.domain.review import ReviewDecision, ReviewRecord
from vera.knowledge_graph.store import KnowledgeGraphStore
from vera.retrieval.resources import load_evidence_directory
from vera.retrieval.subjects import IDENTIFIERS
from vera.stream.parsers import load_events
from vera.workflow.orchestrator import VeraOrchestrator

TOP_K = 5
CASES = (
    ("T1059.001", "What is documented about T1059.001?"),
    ("T1046", "What is documented about T1046?"),
    ("T1110", "What is documented about T1110?"),
    ("CWE-79", "What is documented about CWE-79?"),
    ("CWE-89", "What is documented about CWE-89?"),
    ("CWE-287", "What is documented about CWE-287?"),
    ("T1059.001", "Define PowerShell."),
    ("T1078", "Define Valid Accounts."),
    ("T1082", "Define System Information Discovery."),
    ("T1021", "Define Remote Services."),
    ("T1486", "Define Data Encrypted for Impact."),
    ("T1566", "Define Phishing."),
)


def target_record(evidence: Evidence, target: str) -> bool:
    identifiers = {match.upper() for match in IDENTIFIERS.findall(evidence.title)}
    return "—" not in evidence.title and target in identifiers


def observe(settings: Settings, target: str, query: str) -> dict:
    with VeraOrchestrator(settings) as engine:
        result = engine.analyze({"query": query})
        graph = result.metadata["knowledge_graph"]
        if graph.get("error"):
            raise RuntimeError(graph["error"])
        available = [
            item for item in result.evidence
            if item.status == EvidenceStatus.AVAILABLE
            and item.source not in {SourceType.MEMORY, SourceType.STREAM}
            and not item.metadata.get("fallback")
        ]
        expected = {item.id for item in available if target_record(item, target)}
        claims = result.claims if isinstance(result, AnalysisResult) else result.draft.claims
        cited = {
            citation.evidence_id
            for claim in claims if claim.status == ClaimStatus.SUPPORTED_FACT
            for citation in claim.citations
        }
        verified = result.reflection.validation_failures == 0
        trace = (
            result.trace if isinstance(result, AnalysisResult)
            else engine.review_service.snapshot(result.run_id).values["trace"]
        )
        return {
            "query": query,
            "target": target,
            "hit_at_1": bool(available and available[0].id in expected),
            "hit_at_5": any(item.id in expected for item in available[:TOP_K]),
            "target_cited": verified and bool(expected & cited),
            "graph_attempted": graph["attempted"],
            "graph_cited": verified and bool(set(graph["cited_evidence_ids"]) & cited),
            "validation_failures": result.reflection.validation_failures,
            "review_required": isinstance(result, ReviewRecord),
            "evidence_titles": [item.title for item in available[:TOP_K]],
            "cited_titles": [item.title for item in available if item.id in cited],
            "graph_target_cited": verified and bool(
                expected & cited & set(graph["cited_evidence_ids"])
            ),
            "graph_seed_ids": graph.get("seed_ids", []),
            "graph_projection": graph.get("projection"),
            "trace": trace,
        }


def observe_review(settings: Settings) -> dict:
    path = Path(str(resource("samples/syn-flood.jsonl")))
    events = load_events(path, settings.max_events)
    with VeraOrchestrator(settings) as engine:
        graph = KnowledgeGraphStore(settings)
        before = graph.status().counts["Run"]
        draft = engine.analyze({
            "query": "Summarize this simulated event replay.",
            "events": events,
            "simulated": True,
        })
        if not isinstance(draft, ReviewRecord):
            raise RuntimeError("The replay did not enter human review")
        pending_published = engine.get_run(draft.run_id) is not None
        pending = graph.status().counts["Run"]
        decision = ReviewDecision(
            action="reject", decision_id=uuid4(), version=draft.version,
            feedback="Close the synthetic demonstration without publishing.",
        )
        rejected = engine.decide_review(draft.run_id, decision)
        if not isinstance(rejected, ReviewRecord):
            raise RuntimeError("The rejected draft produced a published report")
        return {
            "fixture": path.name,
            "events": len(events),
            "route": draft.route,
            "rules": [alert.rule_id for alert in draft.incident.alerts] if draft.incident else [],
            "review_reasons": draft.reasons,
            "states": [draft.status, rejected.status],
            "published_before_decision": pending_published,
            "published_after_rejection": engine.get_run(draft.run_id) is not None,
            "graph_run_counts": [before, pending, graph.status().counts["Run"]],
        }


def main() -> None:
    for name in tuple(os.environ):
        if name.startswith("VERA_"):
            del os.environ[name]
    with TemporaryDirectory(prefix="vera-graph-probe-") as temp:
        directory = Path(temp)
        settings = Settings(
            _env_file=None, db_path=directory / "runs.db", corpus_dir=directory / "corpus",
            llm_provider="deterministic", live_sources=False, web_search_enabled=False,
            react_enabled=False, embedding_backend="hash", memory_k=0, retrieval_k=TOP_K,
            kg_hops=1, kg_max_results=12,
        )
        observations = run_comparison(settings, directory)
        print(json.dumps(observations, indent=2))


def run_comparison(settings: Settings, directory: Path) -> dict:
    snapshot = directory / "snapshot.kuzu"
    status = KnowledgeGraphStore(settings.model_copy(update={"kg_path": snapshot})).build([
        item for name in ("knowledge", "corpus") for item in load_evidence_directory(name)
    ])
    if not status.available:
        raise RuntimeError(status.error or "Knowledge graph is unavailable")
    observations: dict = {"snapshot_counts": status.counts, "rows": {}}
    for enabled in (False, True):
        rows = []
        for index, (target, query) in enumerate(CASES):
            path = directory / f"graph-{index}.kuzu"
            if enabled:
                copyfile(snapshot, path)
            configured = settings.model_copy(update={
                "db_path": directory / f"run-{int(enabled)}-{index}.db",
                "kg_enabled": enabled, "kg_path": path,
            })
            rows.append(observe(configured, target, query))
        observations["rows"]["kg_on" if enabled else "kg_off"] = rows
    review_path = directory / "review.kuzu"
    copyfile(snapshot, review_path)
    observations["review_example"] = observe_review(settings.model_copy(update={
        "db_path": directory / "review.db", "kg_enabled": True, "kg_path": review_path,
    }))
    return observations


if __name__ == "__main__":
    main()
