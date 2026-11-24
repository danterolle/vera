import hashlib
import json
import re
from pathlib import Path

from vera.domain.enums import SourceType
from vera_domain.acquire import SNAPSHOTS
from vera_domain.models import SourceFragment, fingerprint

IDENTIFIER = re.compile(r"\b(?:CVE-\d{4}-\d{4,19}|CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?)\b")
OWASP_ID = re.compile(r"\bA\d{2}:\d{2,4}\b")
TECHNIQUE = re.compile(r"^T\d{4}(?:\.\d{3})?$")
CVE = re.compile(r"^CVE-\d{4}-\d{4,19}$")
CWE = re.compile(r"^CWE-\d+$")
CAPEC = re.compile(r"^CAPEC-\d+$")


def excerpt(text: str, maximum: int = 520) -> str | None:
    if not isinstance(text, str):
        return None
    text = text.strip()
    for paragraph in text.split("\n\n"):
        if "```" in paragraph or paragraph.startswith(("http", "|", "<")):
            continue
        if 45 <= len(paragraph) <= maximum:
            return paragraph
        selected = None
        for match in re.finditer(r"[.!?](?:\s+|$)", paragraph):
            candidate = paragraph[:match.start() + 1]
            if len(candidate) > maximum:
                break
            if candidate.endswith(("e.g.", "i.e.", "U.S.")):
                continue
            balanced = all(candidate.count(left) == candidate.count(right)
                           for left, right in (("(", ")"), ("[", "]")))
            if len(candidate) >= 45 and balanced and candidate.count("`") % 2 == 0:
                selected = candidate
        if selected:
            return selected
    return None


def select_content(text: str, maximum: int = 520) -> str | None:
    selected = excerpt(text, maximum)
    if selected is not None:
        return selected
    cleaned = " ".join(text.split())
    return cleaned if 20 <= len(cleaned) <= 900 else None


def load_fragments(
    directory: Path, bundled: Path | None = None,
) -> tuple[list[SourceFragment], dict]:
    attack = json.loads((directory / "attack.json").read_text())
    kev = json.loads((directory / "kev.json").read_text())
    candidates: list[tuple[int, SourceFragment]] = []
    if bundled is not None:
        candidates.extend((0, item) for item in _bundled_fragments(bundled))
    candidates.extend((1, item) for item in _kev_fragments(kev))
    candidates.extend((2, item) for item in _attack_fragments(attack))
    by_text: dict[str, tuple[int, SourceFragment]] = {}
    for priority, item in sorted(candidates, key=lambda value: (value[0], value[1].id)):
        key = " ".join(item.content.casefold().split())
        by_text.setdefault(key, (priority, item))
    selected = [item for _, item in by_text.values()]
    result = sorted(selected, key=lambda value: value.id)
    if len({item.id for item in result}) != len(result):
        raise ValueError("Normalized source-fragment IDs are not unique")
    counts = {
        "attack_objects": len(attack["objects"]),
        "kev_records": len(kev["vulnerabilities"]),
        "kev_version": kev["catalogVersion"],
        "kev_published": kev["dateReleased"],
        "fragments": len(result),
        "bundled_fragments": sum(1 for priority, _ in candidates if priority == 0),
        "duplicate_generic_fragments_removed": len(candidates) - len(result),
    }
    return result, counts


def _kev_fragments(payload: dict) -> list[SourceFragment]:
    result = []
    for index, record in enumerate(payload["vulnerabilities"]):
        entity = record["cveID"]
        family = "product:" + re.sub(
            r"\W+", "-", f"{record['vendorProject']}:{record['product']}".lower(),
        )
        for field, category in (
            ("shortDescription", "vulnerability"), ("requiredAction", "remediation"),
        ):
            original = record[field]
            content = select_content(original)
            if content is None:
                continue
            result.append(SourceFragment(
                id=_fragment_id("kev", index, field, content),
                entity_id=entity, family=family, category=category, source=SourceType.CISA_KEV,
                title=f"{entity} | {record['vulnerabilityName']}"[:230],
                content=content, original=original,
                field_path=f"vulnerabilities[{index}].{field}",
                source_url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                snapshot="kev", revision=SNAPSHOTS["kev"]["revision"],
                tags=[f"catalog:{payload['catalogVersion']}", f"added:{record['dateAdded']}",
                      f"ransomware:{record['knownRansomwareCampaignUse']}",
                      *record.get("cwes", [])],
            ))
    return result


def _attack_fragments(payload: dict) -> list[SourceFragment]:
    result = []
    techniques = {}
    for index, record in enumerate(payload["objects"]):
        if (record.get("type") != "attack-pattern" or record.get("revoked")
                or record.get("x_mitre_deprecated")):
            continue
        reference = next(
            (item for item in record.get("external_references", [])
             if item.get("source_name") == "mitre-attack" and item.get("external_id")), None,
        )
        if reference is None:
            continue
        entity = reference["external_id"]
        techniques[record["id"]] = (entity, record["name"], reference["url"])
        content = select_content(record.get("description", ""))
        if content is None:
            continue
        result.append(SourceFragment(
            id=_fragment_id("attack", index, "description", content),
            entity_id=entity, family=f"technique:{entity.split('.')[0]}",
            category="technique", source=SourceType.MITRE_ATTACK,
            title=f"{entity} | {record['name']}", content=content,
            original=record.get("description", ""),
            field_path=f"objects[{index}].description", source_url=reference["url"],
            snapshot="attack", revision=SNAPSHOTS["attack"]["revision"],
            tags=[f"modified:{record.get('modified', '')}",
                  *[f"tactic:{phase['phase_name']}"
                    for phase in record.get("kill_chain_phases", [])],
                  *[f"platform:{platform}" for platform in record.get("x_mitre_platforms", [])]],
        ))
    for index, record in enumerate(payload["objects"]):
        if (record.get("type") != "relationship" or record.get("relationship_type") != "mitigates"
                or record.get("revoked") or record.get("x_mitre_deprecated")
                or record.get("target_ref") not in techniques):
            continue
        content = select_content(record.get("description", ""))
        if content is None:
            continue
        entity, name, url = techniques[record["target_ref"]]
        result.append(SourceFragment(
            id=_fragment_id("attack-rel", index, "description", content),
            entity_id=entity, family=f"technique:{entity.split('.')[0]}",
            category="mitigation", source=SourceType.MITRE_ATTACK,
            title=f"{entity} | Mitigation relationship for {name}"[:230],
            content=content, original=record.get("description", ""),
            field_path=f"objects[{index}].description", source_url=url,
            snapshot="attack", revision=SNAPSHOTS["attack"]["revision"],
            tags=[f"modified:{record.get('modified', '')}"],
        ))
    return result


def _bundled_fragments(directory: Path) -> list[SourceFragment]:
    result = []
    for path in sorted(directory.glob("*.json")):
        revision = hashlib.sha256(path.read_bytes()).hexdigest()[:40]
        for index, record in enumerate(json.loads(path.read_text())):
            content = select_content(record.get("content", ""))
            if content is None:
                continue
            title = record.get("title", "")
            metadata = record.get("metadata") or {}
            entity = _bundled_entity(title, metadata)
            category = _bundled_category(title, metadata)
            result.append(SourceFragment(
                id=_fragment_id("corpus", index, path.name, content),
                entity_id=entity, family=_bundled_family(entity, category),
                category=category, source=SourceType(record["source"]),
                title=title[:300], content=content,
                original=record.get("content", ""),
                field_path=f"corpus/{path.name}[{index}]",
                source_url=record.get("url") or "",
                snapshot="bundled-corpus", revision=revision,
                tags=[*metadata.get("keywords", []), *metadata.get("aliases", []),
                      *IDENTIFIER.findall(title)],
            ))
    return result


def _fragment_id(snapshot: str, index: int, field: str, content: str) -> str:
    identity = fingerprint({"snapshot": snapshot, "index": index, "field": field,
                            "content": content})
    return f"src-{identity[:24]}"


def _bundled_entity(title: str, metadata: dict) -> str:
    for key in ("external_id", "technique_id", "cwe_id", "cve_id"):
        if metadata.get(key):
            return str(metadata[key])
    if " — " in title:
        tail = title.rsplit(" — ", 1)[-1]
        found = IDENTIFIER.search(tail) or OWASP_ID.search(tail)
        if found:
            return found.group(0)
    found = IDENTIFIER.search(title) or OWASP_ID.search(title)
    if found:
        return found.group(0)
    return re.sub(r"\W+", "-", title.casefold()).strip("-")[:80] or "unknown"


def _bundled_category(title: str, metadata: dict) -> str:
    if " — mitigates — " in title:
        return "mitigation"
    if " — uses — " in title:
        return "usage"
    if "mapped weaknesses" in title.casefold():
        return "mapping"
    prefix = title.split(" ", 1)[0]
    if TECHNIQUE.match(prefix):
        return "technique"
    if CVE.match(prefix):
        return "vulnerability"
    if CWE.match(prefix) or CAPEC.match(prefix):
        return "weakness"
    if prefix == "OWASP" or prefix == "NIST":
        return "guidance"
    if prefix.startswith(("TA", "M", "G", "S")) and prefix[1:].isdigit():
        return {"TA": "tactic", "M": "mitigation", "G": "group", "S": "software"}[prefix[0]]
    return "guidance"


def _bundled_family(entity: str, category: str) -> str:
    if entity.startswith("T"):
        return f"technique:{entity.split('.')[0]}"
    if entity.startswith("CVE-"):
        return f"cve:{entity.split('-')[1]}"
    if entity.startswith("CWE-"):
        return "cwe"
    if entity.startswith("CAPEC-"):
        return "capec"
    if OWASP_ID.match(entity):
        return "owasp"
    if entity.lower().startswith("nist"):
        return "nist"
    return category
