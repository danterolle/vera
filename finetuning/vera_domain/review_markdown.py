CHECKLIST = (
    "Every `supported_fact` is supported by the quoted evidence.",
    "Every quotation is a verbatim substring of its cited evidence.",
    "The summary does not assert local compromise, exposure or deployment.",
    "Scope and conversational intent match the request.",
    "For `stream_triage`, claims match the supplied detector output.",
    "Entity, title and response language are correct.",
)


def render(cases: list[dict], report: dict) -> str:
    lines = [
        "# VERA v4 target review", "",
        f"Dataset `{report['dataset_version']}` · `{report['dataset_sha256'][:16]}…` · "
        f"{report['examples']} cases · seed {report['seed']}", "",
        "This pack supports a human decision. It does not authorize training by itself.", "",
        "## How to review", "",
        "1. For each case, compare the target with the supplied context evidence.",
        "2. Edit `review.verdict` in `cases.jsonl`: `accept`, `fix` or `reject`.",
        "3. Add `review.reviewer`, `review.notes` and `review.reviewed_at`;",
        "   `fix` and `reject` require notes.",
        "4. Fill `signoff.json` with the reviewer and date.",
        "5. Run `uv run python finetuning/prepare_review_pack.py --summarize <dir>`;",
        "   `ready_for_authorization` is true only when every case is accepted.", "",
        "## Checklist", "",
        *[f"- [ ] {item}" for item in CHECKLIST], "",
        "## Cases", "",
    ]
    for case in cases:
        checks = ", ".join(
            f"{name}={'ok' if value is True else 'FAIL'}"
            for name, value in case["automated_checks"].items()
        )
        lines.extend([
            f"### {case['review_id']} · {case['task']} · {case['split']}", "",
            f"**Question:** {case['question']}", "",
            f"**Intent / language:** {case['intent']} / {case['language']}", "",
            f"**Target summary:** {case['target'].get('summary', '')}", "",
            "| Status | Claim | Citations |", "| --- | --- | --- |",
            *[
                f"| {claim['status']} | {_cell(claim['text'])} | "
                f"{', '.join(c['evidence_id'] for c in claim.get('citations', [])) or '—'} |"
                for claim in case["target"].get("claims", [])
            ],
            "", "**Evidence**", "",
        ])
        if case["evidence"]:
            lines.extend(
                f"- `{identifier}` · {_cell(item.get('source', ''))} · "
                f"{_cell(item.get('title', ''))}: {_cell(item.get('content', ''))}"
                for identifier, item in case["evidence"].items()
            )
        else:
            lines.append("- None supplied (social or clarification turn).")
        lines.extend([
            "", f"**Automated checks:** {checks}", "",
            "**Verdict:** ☐ accept · ☐ fix · ☐ reject  ",
            "**Notes:** ", "",
        ])
    return "\n".join(lines) + "\n"


def _cell(text: str, limit: int = 400) -> str:
    collapsed = " ".join(str(text).split()).replace("|", "\\|")
    return (collapsed[:limit] + "…") if len(collapsed) > limit else collapsed
