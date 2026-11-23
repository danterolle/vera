import json
import re

CHECKLIST = (
    "Every supported_fact is relevant to the question and supported by its own citation.",
    "Every quotation and supported_fact text is verbatim in the cited evidence.",
    "The complete summary is correct, useful and does not overstate local impact.",
    "Scope and conversational intent match the request.",
    "Abstentions explain missing evidence without substituting an unrelated record.",
    "User-facing prose follows the configured response language; quotations stay verbatim.",
    "Fallbacks, validation repairs and remaining gaps are assessed explicitly.",
)


def block(text: str) -> str:
    longest = max((len(match) for match in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}\n"


def render_case(case: dict) -> str:
    lines = [
        f"### {case['id']} - {case['task']} - expected scope: {case['expect_scope']}",
        "",
        f"Model: `{case['model']}`; HTTP {case['http_status']}; "
        f"{case['seconds']}s; run `{case['run_id']}`.",
        "",
        "**Question**",
        block(case["query"]),
        f"Observed `out_of_scope`: `{json.dumps(case.get('out_of_scope'))}`.",
    ]
    if case.get("conversation"):
        lines.extend([
            "**Supplied conversation**", block(json.dumps(case["conversation"], indent=2)),
        ])
    if "rubric" in case:
        lines.extend(["**Frozen expectations**", block(json.dumps(case["rubric"], indent=2))])
        if case["note"]:
            lines.extend(["**Case notes**", block(case["note"])])
    lines.extend(["**Complete summary**", block(case["summary"])])
    if case.get("events"):
        lines.extend(["**Detector report**", block(json.dumps(case.get("incident"), indent=2))])
    for label, key in (
        ("Claims and citations", "claims"), ("Complete supplied evidence", "evidence"),
        ("Reflection", "reflection"), ("Warnings", "warnings"), ("Review reasons", "reasons"),
        ("Runtime provenance", "metadata"),
    ):
        lines.extend([f"**{label}**", block(json.dumps(case[key], ensure_ascii=False, indent=2))])
    lines.extend(["**Verdict:** accept / fix / reject", "**Notes:**", ""])
    return "\n".join(lines)
