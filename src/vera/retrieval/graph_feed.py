from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence

PREDICATES = {"mitigates": "mitigates", "uses": "uses", "subtechnique-of": "subtechnique_of"}


def attack_relations(
    objects: list[dict], documents: list[Evidence], version: str
) -> list[Evidence]:
    by_stix = {record.metadata["stix_id"]: record for record in documents}
    identities = {key: record.metadata["external_id"] for key, record in by_stix.items()}
    names = {record.metadata["external_id"]: record.title for record in documents}
    tactics = {
        item.get("x_mitre_shortname"): identities[item["id"]]
        for item in objects
        if item.get("type") == "x-mitre-tactic" and item.get("id") in identities
    }
    for item in objects:
        if item.get("type") != "attack-pattern" or item.get("id") not in identities:
            continue
        document = by_stix[item["id"]]
        mappings = [
            {
                "subject": identities[item["id"]],
                "object": tactics[phase["phase_name"]],
                "subject_name": document.title,
                "object_name": names[tactics[phase["phase_name"]]],
                "predicate": "part_of",
                "field_path": "STIX.kill_chain_phases",
            }
            for phase in item.get("kill_chain_phases", [])
            if phase.get("kill_chain_name") == "mitre-attack" and phase.get("phase_name") in tactics
        ]
        if mappings:
            document.metadata["graph_relations"] = mappings
    records = []
    for item in objects:
        if (
            item.get("type") != "relationship"
            or item.get("revoked")
            or item.get("x_mitre_deprecated")
        ):
            continue
        predicate = PREDICATES.get(item.get("relationship_type"))
        subject = identities.get(item.get("source_ref"))
        target = identities.get(item.get("target_ref"))
        if not predicate or not subject or not target:
            continue
        # Retain the original structured payload, not invented natural-language facts.
        content = str(item.get("description") or "ATT&CK structured relationship record.")[:11_000]
        records.append(
            make_evidence(
                SourceType.MITRE_ATTACK,
                f"{names[subject]} — {predicate} — {names[target]}"[:300],
                content,
                url=by_stix[item["source_ref"]].url,
                metadata={
                    "stix_id": item.get("id"),
                    "modified": item.get("modified"),
                    "attack_version": version,
                    "provenance": "synchronized_feed",
                    "graph_relations": [
                        {
                            "subject": subject,
                            "object": target,
                            "subject_name": names[subject],
                            "object_name": names[target],
                            "predicate": predicate,
                            "field_path": "STIX.source_ref/relationship_type/target_ref",
                            "supporting_quote": content[:4000] if item.get("description") else "",
                        }
                    ],
                    "keywords": [subject, target],
                },
            )
        )
    return records
