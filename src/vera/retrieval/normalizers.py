from typing import Any

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence, make_evidence

ATTACK_TYPES = {
    "attack-pattern": "technique",
    "course-of-action": "mitigation",
    "intrusion-set": "group",
    "malware": "software",
    "tool": "software",
    "x-mitre-tactic": "tactic",
}
CISA_KEV_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/"
    "known_exploited_vulnerabilities.json"
)


def normalize_attack(payload: dict[str, Any]) -> tuple[list[Evidence], str]:
    objects = payload.get("objects")
    if not isinstance(objects, list):
        raise ValueError("ATT&CK feed has no objects list")
    collection = next(
        (item for item in objects if item.get("type") == "x-mitre-collection"),
        {},
    )
    version = str(collection.get("x_mitre_version", "unknown"))
    documents = []
    for item in objects:
        object_type = item.get("type")
        if object_type not in ATTACK_TYPES:
            continue
        if item.get("revoked") or item.get("x_mitre_deprecated"):
            continue
        reference = _attack_reference(item.get("external_references", []))
        if reference is None:
            continue
        external_id, url = reference
        name = str(item.get("name") or external_id)
        description = str(item.get("description") or name)[:11_000]
        keywords = [
            *item.get("x_mitre_platforms", []),
            *item.get("aliases", []),
            *[
                phase.get("phase_name", "")
                for phase in item.get("kill_chain_phases", [])
                if isinstance(phase, dict)
            ],
        ]
        documents.append(
            make_evidence(
                SourceType.MITRE_ATTACK,
                f"{external_id} - {name}",
                description,
                url=url,
                metadata={
                    "external_id": external_id,
                    "object_type": ATTACK_TYPES[object_type],
                    "stix_id": item.get("id"),
                    "modified": item.get("modified"),
                    "attack_version": version,
                    "provenance": "synchronized_feed",
                    "keywords": [value for value in keywords if value],
                },
            )
        )
    return documents, version


def normalize_cisa_kev(payload: dict[str, Any]) -> tuple[list[Evidence], str]:
    records = payload.get("vulnerabilities")
    if not isinstance(records, list):
        raise ValueError("CISA KEV feed has no vulnerabilities list")
    version = str(payload.get("catalogVersion", "unknown"))
    documents = []
    for item in records:
        cve_id = str(item.get("cveID", "")).upper()
        if not cve_id:
            continue
        name = str(item.get("vulnerabilityName") or cve_id)
        description = str(item.get("shortDescription") or "No description provided.")
        action = str(item.get("requiredAction") or "No required action provided.")
        content = (
            f"{description} CISA required action: {action} "
            f"Date added: {item.get('dateAdded', 'unknown')}; "
            f"due date: {item.get('dueDate', 'unknown')}; "
            f"known ransomware use: {item.get('knownRansomwareCampaignUse', 'unknown')}."
        )
        documents.append(
            make_evidence(
                SourceType.CISA_KEV,
                f"{cve_id} - {name}",
                content,
                url=CISA_KEV_URL,
                metadata={
                    "cve_id": cve_id,
                    "catalog_version": version,
                    "vendor": item.get("vendorProject"),
                    "product": item.get("product"),
                    "date_added": item.get("dateAdded"),
                    "due_date": item.get("dueDate"),
                    "cwes": item.get("cwes", []),
                    "provenance": "synchronized_feed",
                    "keywords": [
                        str(item.get("vendorProject") or ""),
                        str(item.get("product") or ""),
                    ],
                },
            )
        )
    return documents, version


def _attack_reference(references: list[dict[str, Any]]) -> tuple[str, str] | None:
    for reference in references:
        if reference.get("source_name") != "mitre-attack":
            continue
        external_id = reference.get("external_id")
        url = reference.get("url")
        if external_id and url:
            return str(external_id), str(url)
    return None
