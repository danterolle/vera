import re

from vera.domain.enums import EvidenceStatus, SourceType
from vera.domain.evidence import Evidence
from vera.knowledge_graph.models import Entity, Relation

IDENTIFIER = re.compile(
    r"\b(?:CVE-\d{4}-\d{4,19}|CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?|[MGS]\d{4}|TA\d{4})\b",
    re.IGNORECASE,
)
ATTACK_KIND = {"T": "technique", "TA": "tactic", "M": "mitigation", "G": "group", "S": "software"}


def entity(identifier: str, name: str | None = None, aliases: list[str] | None = None) -> Entity:
    if re.fullmatch(r"(?:concept|guidance):[a-z0-9][a-z0-9:._-]{0,180}", identifier):
        return Entity(
            id=identifier,
            kind=identifier.split(":")[0],
            name=name or identifier,
            aliases=aliases or [],
        )
    identifier = identifier.upper()
    if IDENTIFIER.fullmatch(identifier) is None:
        raise ValueError(f"Invalid graph identifier: {identifier}")
    if identifier.startswith(("CVE-", "CWE-", "CAPEC-")):
        kind = identifier.split("-")[0].lower()
        key = identifier
    else:
        prefix = "TA" if identifier.startswith("TA") else identifier[0]
        kind = ATTACK_KIND[prefix]
        key = f"attack:enterprise:{identifier}"
    return Entity(id=key, kind=kind, name=(name or identifier)[:300], aliases=aliases or [])


def seeds(query: str) -> list[str]:
    return list(dict.fromkeys(entity(item).id for item in IDENTIFIER.findall(query)))[:8]


def entities(record: Evidence) -> list[Entity]:
    values = []
    for key in ("cve_id", "cwe_id", "technique_id", "external_id"):
        identifier = record.metadata.get(key)
        if isinstance(identifier, str) and IDENTIFIER.fullmatch(identifier):
            values.append(entity(identifier, record.title, record.metadata.get("aliases", [])))
    for mapping in record.metadata.get("graph_entities", []):
        values.append(entity(mapping["id"], mapping["name"], mapping.get("aliases", [])))
    return list({value.id: value for value in values}.values())


def relations(record: Evidence) -> list[Relation]:
    if record.status != EvidenceStatus.AVAILABLE or record.source == SourceType.MEMORY:
        return []
    result = []
    if record.source == SourceType.MITRE_ATTACK:
        for current in entities(record):
            code = current.id.rsplit(":", 1)[-1]
            if current.kind == "technique" and "." in code:
                result.append(
                    Relation(
                        subject=current,
                        object=entity(code.split(".")[0]),
                        predicate="subtechnique_of",
                        field_path="metadata.external_id",
                    )
                )
    for mapping in record.metadata.get("graph_relations", []):
        result.append(
            Relation(
                subject=entity(mapping["subject"], mapping.get("subject_name")),
                object=entity(mapping["object"], mapping.get("object_name")),
                predicate=mapping["predicate"],
                field_path=mapping["field_path"],
                supporting_quote=str(mapping.get("supporting_quote", ""))[:4000],
            )
        )
    if record.source in {SourceType.NVD, SourceType.CVE_ORG, SourceType.CISA_KEV}:
        cve = record.metadata.get("cve_id")
        if isinstance(cve, str) and IDENTIFIER.fullmatch(cve):
            for code in record.metadata.get("cwes", []):
                if isinstance(code, str) and re.fullmatch(r"CWE-\d+", code):
                    result.append(
                        Relation(
                            subject=entity(cve),
                            object=entity(code),
                            predicate="has_weakness",
                            field_path="metadata.cwes",
                        )
                    )
    return result
