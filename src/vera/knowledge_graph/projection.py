import json
from hashlib import sha256

from vera.domain.enums import SourceType
from vera.domain.evidence import Evidence
from vera.domain.reports import AnalysisResult
from vera.domain.requests import AnalysisRequest
from vera.knowledge_graph.entity_write import put_entity
from vera.knowledge_graph.models import Relation
from vera.knowledge_graph.normalization import entities, entity, relations

RETRIEVAL_FIELDS = {
    "retrieval_score",
    "lexical_score",
    "vector_score",
    "quality_score",
    "freshness_score",
    "novelty_score",
    "selection_score",
}


def fingerprint(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def merge_node(conn, label: str, key: str, values: dict) -> None:
    # Label/key/property names only originate from this module, never user input.
    assignments = ", ".join(f"n.{name} = ${name}" for name in values if name != key)
    conn.execute(f"MERGE (n:{label} {{{key}: ${key}}}) ON CREATE SET {assignments}", values).close()


def merge_edge(conn, source: str, target: str, relation: str, left: str, right: str) -> None:
    source_key = "record_key" if source == "SourceRecord" else "id"
    target_key = "record_key" if target == "SourceRecord" else "id"
    conn.execute(
        f"MATCH (a:{source} {{{source_key}: $left}}), (b:{target} {{{target_key}: $right}}) "
        f"MERGE (a)-[:{relation}]->(b)",
        {"left": left, "right": right},
    ).close()


def record_payload(record: Evidence) -> dict:
    payload = record.model_dump(mode="json")
    payload["id"] = record.metadata.get("kg_original_evidence_id", record.id)
    # Retrieval annotations are not upstream identity. Observation dates live in metadata.
    payload["metadata"] = {
        key: value
        for key, value in payload["metadata"].items()
        if key not in RETRIEVAL_FIELDS and not key.startswith("kg_")
    }
    return payload


def record_key(record: Evidence) -> str:
    return fingerprint(
        {key: value for key, value in record_payload(record).items() if key != "retrieved_at"}
    )


def put_record(conn, record: Evidence) -> str | None:
    if record.source == SourceType.MEMORY:
        return None
    payload = record_payload(record)
    key = record_key(record)
    merge_node(
        conn,
        "SourceRecord",
        "record_key",
        {
            "record_key": key,
            "evidence_id": payload["id"],
            "source": record.source.value,
            "status": record.status.value,
            "url": record.url,
            "content": record.content,
            "title": record.title,
            "payload_json": json.dumps(payload, sort_keys=True),
        },
    )
    for value in entities(record):
        put_entity(conn, value)
        merge_edge(conn, "SourceRecord", "Entity", "DESCRIBES", key, value.id)
    for relation in relations(record):
        put_relation(conn, relation, key, record)
    return key


def put_relation(conn, relation: Relation, record_key: str, record: Evidence) -> None:
    if relation.supporting_quote and relation.supporting_quote not in record.content:
        raise ValueError("Graph supporting quotation is absent from source record")
    payload = relation.model_dump(mode="json")
    for endpoint in ("subject", "object"):
        payload[endpoint].pop("aliases")
    identifier = fingerprint({"relation": payload, "record": record_key})
    put_entity(conn, relation.subject)
    put_entity(conn, relation.object)
    merge_node(
        conn,
        "Assertion",
        "id",
        {
            "id": identifier,
            "predicate": relation.predicate,
            "status": relation.status.value,
        },
    )
    merge_edge(conn, "Assertion", "Entity", "SUBJECT", identifier, relation.subject.id)
    merge_edge(conn, "Assertion", "Entity", "OBJECT", identifier, relation.object.id)
    conn.execute(
        "MATCH (a:Assertion {id: $id}), (r:SourceRecord {record_key: $record}) "
        "MERGE (a)-[s:SUPPORTED_BY]->(r) "
        "ON CREATE SET s.supporting_quote = $quote, s.field_path = $field",
        {
            "id": identifier,
            "record": record_key,
            "quote": relation.supporting_quote,
            "field": relation.field_path,
        },
    ).close()


def put_run(conn, request: AnalysisRequest, result: AnalysisResult) -> None:
    merge_node(conn, "Run", "id", {"id": result.run_id, "session_id": request.session_id})
    for record in result.evidence:
        if key := put_record(conn, record):
            merge_edge(conn, "Run", "SourceRecord", "USED_RECORD", result.run_id, key)
    alerts = result.incident.alerts if result.incident else []
    # Retain only events needed to audit alerts; event IDs keep their original indexes.
    indexes = sorted({index for alert in alerts for index in alert.event_indexes})
    for index in indexes:
        event = request.events[index]
        key = f"{result.run_id}:event:{index}"
        status = "simulated" if request.simulated or event.simulated else "system_inference"
        merge_node(
            conn,
            "Event",
            "id",
            {
                "id": key,
                "status": status,
                "payload_json": event.model_dump_json(),
            },
        )
        merge_edge(conn, "Run", "Event", "HAS_EVENT", result.run_id, key)
    for index, alert in enumerate(alerts):
        key = f"{result.run_id}:alert:{index}"
        simulated = request.simulated or any(
            request.events[position].simulated for position in alert.event_indexes
        )
        status = "simulated" if simulated else "system_inference"
        merge_node(
            conn,
            "Alert",
            "id",
            {
                "id": key,
                "rule_id": alert.rule_id,
                "status": status,
                "payload_json": alert.model_dump_json(),
            },
        )
        merge_edge(conn, "Run", "Alert", "HAS_ALERT", result.run_id, key)
        for position in alert.event_indexes:
            merge_edge(
                conn, "Alert", "Event", "TRIGGERED_BY", key, f"{result.run_id}:event:{position}"
            )
        for code in ([alert.technique_id] if alert.technique_id else []) + alert.cve_ids:
            value = entity(code)
            put_entity(conn, value)
            conn.execute(
                "MATCH (a:Alert {id: $alert}), (e:Entity {id: $entity}) "
                "MERGE (a)-[s:SUGGESTS]->(e) ON CREATE SET s.status = $status",
                {"alert": key, "entity": value.id, "status": status},
            ).close()
