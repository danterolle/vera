from vera.domain.enums import ClaimStatus, EvidenceStatus, SourceType
from vera.domain.state import GraphState
from vera.retrieval.subjects import normalized


def validated_knowledge(state: GraphState) -> tuple[list, dict]:
    """Only cited, validated online context may add domain knowledge."""
    plan = state["resource_plan"]
    allowed = plan.intent == "cybersecurity" and not state["draft"].out_of_scope
    cited = {
        citation.evidence_id
        for claim in state["draft"].claims if claim.status == ClaimStatus.SUPPORTED_FACT
        for citation in claim.citations
    } if allowed and not state["validation_errors"] else set()
    evidence = []
    learned = set()
    for item in state["evidence"]:
        if item.source == SourceType.WEB and not item.metadata.get("kg_record_key"):
            accepted = (item.id in cited and item.status == EvidenceStatus.AVAILABLE
                        and item.metadata.get("scope_validated") is True)
            metadata = {**item.metadata, "learning_validated": bool(accepted)}
            if accepted:
                topic = str(item.metadata.get("validated_topic") or plan.subject or item.title)
                slug = normalized(topic).replace(" ", "-")[:140]
                if slug:
                    key = f"concept:web:{slug}"
                    metadata["graph_entities"] = [{
                        "id": key, "name": topic[:300], "aliases": [topic, item.title],
                    }]
                    learned.add(key)
            item = item.model_copy(update={"metadata": metadata})
        evidence.append(item)
    return evidence, {
        "validated_entity_ids": sorted(learned),
        "policy": "cybersecurity scope, relevant source, supported citation, finalized report",
    }
