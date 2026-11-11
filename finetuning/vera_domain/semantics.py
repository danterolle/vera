import re

TECHNIQUE = re.compile(r"T\d{4}(?:\.\d{3})?")

FORBIDDEN = {
    "affected assets": "vulnerability-specific asset wording",
    "affected versions": "vulnerability-specific version wording",
    "asset-specific priority": "vulnerability-specific priority wording",
    "documented issues": "vulnerability-specific issue wording",
    "local exposure": "vulnerability-specific exposure wording",
}


def audit_technique_wording(
    task: str, entities: list[str], query: str, summary: str,
) -> None:
    if not any(TECHNIQUE.fullmatch(entity) for entity in entities):
        return
    text = f"{query} {summary}".casefold()
    for phrase, label in FORBIDDEN.items():
        if phrase in text:
            raise ValueError(f"{task} uses {label}: {phrase!r}")
