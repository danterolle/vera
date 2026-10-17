from vera.domain.evidence import Evidence
from vera.knowledge_graph.projection import record_key


def combine_evidence(graph: list[Evidence], ordinary: list[Evidence]) -> list[Evidence]:
    indexed = {record.metadata["kg_record_key"]: record for record in graph}
    remaining = []
    for record in ordinary:
        key = record_key(record)
        if key not in indexed or record.metadata.get("provenance") == "live_api":
            remaining.append(record)
            continue
        selected = indexed[key]
        indexed[key] = selected.model_copy(
            update={
                "metadata": {**selected.metadata, **record.metadata},
            }
        )
    return list(indexed.values()) + remaining
