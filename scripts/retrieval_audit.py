"""Check whether the runtime retrieval returns records for the scope probe cases.

Compares the hybrid ranker (BM25 plus embeddings) with lexical-only ranking. If the
lexical-only top results already contain the expected entity, the embedding backend
cannot be the cause of a refusal on that case.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "finetuning"))

from vera_finetuning.scope import CASES  # noqa: E402

from vera.config import Settings  # noqa: E402
from vera.retrieval.corpus import LocalCorpus  # noqa: E402
from vera.retrieval.embeddings import build_embedder  # noqa: E402
from vera.retrieval.ranking import Bm25Ranker, normalize  # noqa: E402


def hit(documents, terms: list[str]) -> bool:
    if not terms:
        return False
    text = " ".join(
        f"{document.title} {document.content}".casefold() for document in documents
    )
    return any(term.casefold() in text for term in terms)


def run(backend: str, limit: int = 5) -> dict:
    settings = Settings(_env_file=None).model_copy(update={"embedding_backend": backend})
    corpus = LocalCorpus(build_embedder(settings), None, 0.0)
    lexical_ranker = Bm25Ranker(corpus.documents)
    rows = []
    for case in CASES:
        if case["kind"] != "domain":
            continue
        hybrid = corpus.search(case["query"], limit)
        scores = normalize(lexical_ranker.scores(case["query"]))
        ranked = sorted(
            zip(corpus.documents, scores, strict=True),
            key=lambda item: (-item[1], item[0].title, item[0].id),
        )
        lexical = [document for document, _ in ranked[:limit]]
        rows.append({
            "name": case["name"],
            "query": case["query"],
            "terms": case["terms"],
            "hybrid_hit": hit(hybrid, case["terms"]),
            "lexical_hit": hit(lexical, case["terms"]),
            "same_top": [item.id for item in hybrid] == [item.id for item in lexical],
            "hybrid_top": [item.title for item in hybrid],
            "lexical_top": [item.title for item in lexical],
        })
    return {
        "backend": backend,
        "corpus_documents": len(corpus.documents),
        "domain_cases": len(rows),
        "hybrid_hits": sum(row["hybrid_hit"] for row in rows),
        "lexical_hits": sum(row["lexical_hit"] for row in rows),
        "same_top": sum(row["same_top"] for row in rows),
        "misses": [
            {
                "name": row["name"],
                "hybrid": row["hybrid_top"][:3],
                "lexical": row["lexical_top"][:3],
            }
            for row in rows if not row["hybrid_hit"] or not row["lexical_hit"]
        ],
        "results": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend", choices=("hash", "sentence-transformers"), default="hash",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("--limit must be 1..20")
    if args.output and args.output.exists():
        parser.error("Choose a new report path; existing reports are never overwritten")
    report = run(args.backend, args.limit)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
