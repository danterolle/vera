import json
import re

from vera.knowledge_graph.normalization import seeds


def catalog(conn) -> list[dict]:
    rows = conn.execute("MATCH (e:Entity) RETURN e.id, e.kind, e.name, e.aliases").get_all()
    return [
        {"id": key, "kind": kind, "label": name, "aliases": json.loads(raw or "[]")}
        for key, kind, name, raw in rows
    ]


def names(item: dict) -> set[str]:
    label = re.sub(
        r"^(?:CVE-\d{4}-\d+|CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d+)?)\s*-\s*", "", item["label"]
    )
    # ATT&CK subtechnique titles may include the parent name before a colon.
    return {item["id"], label, label.rsplit(": ", 1)[-1], *item["aliases"]}


def resolve_entities(conn, query: str, limit: int = 8) -> list[str]:
    """Explicit identifiers take precedence; otherwise match complete names/aliases."""
    exact = seeds(query)
    if exact:
        return exact[:limit]
    text = query.casefold().strip()
    ranked = []
    for item in catalog(conn):
        score = max(
            (
                len(name)
                for name in names(item)
                if len(name) >= 3
                and re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", text)
            ),
            default=0,
        )
        if score:
            ranked.append((-score, item["id"]))
    return [key for _, key in sorted(ranked)[:limit]]


def search_entities(conn, query: str, limit: int = 12) -> list[dict]:
    """Bounded suggestions for a partial name, alias, or identifier in the viewer."""
    text = query.casefold().strip()
    if len(text) < 2:
        return []
    matches = []
    for item in catalog(conn):
        alternatives = {name.casefold() for name in names(item)}
        if any(text in name for name in alternatives):
            matches.append((text not in alternatives, item["label"].casefold(), item))
    return [item for _, _, item in sorted(matches, key=lambda row: row[:2])[:limit]]
