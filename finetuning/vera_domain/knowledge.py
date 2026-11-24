import random
from collections import defaultdict

from vera.domain.enums import Route
from vera_domain.compose import Scenario, compose, evidence_for, factual, inference
from vera_domain.knowledge_variants import VARIANTS, variant_scenario
from vera_domain.models import SourceFragment
from vera_domain.phrases import GRAPH, TRIAGE, pick


def knowledge_scenarios(
    fragments: list[SourceFragment], assignments: dict[str, str], split: str, seed: int,
) -> list:
    generator = random.Random(seed)
    entities: dict[str, list[SourceFragment]] = defaultdict(list)
    categories: dict[str, list[SourceFragment]] = defaultdict(list)
    for item in fragments:
        entities[item.entity_id].append(item)
        categories[item.category].append(item)
    records = []
    for index, entity in enumerate(sorted(entities)):
        members = entities[entity]
        primary = next(
            (item for item in members
             if item.category in {"vulnerability", "technique", "weakness"}), None,
        )
        if primary is None:
            continue
        companion = next(
            (item for item in members if item.category in {"remediation", "mitigation"}), None,
        )
        alternatives = [
            item for item in categories[primary.category]
            if item.entity_id != entity and entity not in (item.content + item.title).upper()
        ]
        if not alternatives:
            continue
        common = {tag for tag in primary.tags if tag.startswith(("CWE-", "tactic:", "platform:"))}
        ranked = [
            (10 * (item.family == primary.family) + len(common & set(item.tags)), item)
            for item in alternatives
        ]
        best = max(score for score, _ in ranked)
        distractor = generator.choice([item for score, item in ranked if score == best])
        base = _base(primary, companion, distractor, entity, generator)
        records.append(compose(base, assignments, extra_groups=(assignments[primary.id],)))
        records.append(compose(
            variant_scenario(
                VARIANTS[index % len(VARIANTS)], primary, companion, distractor, entity,
                base, split, generator,
            ),
            assignments, extra_groups=(assignments[primary.id],),
        ))
    return records


def _base(primary, companion, distractor, entity, generator) -> Scenario:
    name = primary.title.split(" | ")[0]
    evidence = [evidence_for(primary)]
    bindings = {evidence[0].id: primary.id}
    claims = [factual(evidence[0])]
    if companion is not None:
        item = evidence_for(companion)
        evidence.append(item)
        bindings[item.id] = companion.id
        claims.append(factual(item))
    decoy = evidence_for(distractor)
    evidence.append(decoy)
    bindings[decoy.id] = distractor.id
    technique = primary.category == "technique"
    claims.append(inference(
        "The supplied documentation is not evidence of local execution or compromise."
        if technique else
        "Affected-version and exposure matching require asset evidence not supplied here."
    ))
    return Scenario(
        task="graph_evidence" if technique else "vulnerability_triage",
        query=pick(generator, GRAPH if technique else TRIAGE, title=name),
        summary=(
            f"The supplied snapshot documents {name} and does not establish local execution "
            "or attribution." if technique else
            f"The supplied snapshot documents {name}; affected versions, exposure and local "
            "exploitation remain unconfirmed."
        ),
        evidence=evidence, claims=claims, entities=[entity], bindings=bindings,
        route=Route.CAG_RAG if technique else Route.CAG_RAG_TOOL,
    )
