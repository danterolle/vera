import random
from collections import defaultdict

from vera.domain.enums import Route
from vera.domain.requests import ConversationMessage
from vera_domain.compose import (
    Scenario,
    compose,
    evidence_for,
    factual,
    inference,
    unavailable,
)
from vera_domain.phrases import (
    CLARIFY,
    CONCEPT,
    DEFENSIVE,
    LANGUAGES,
    SOCIAL,
    display_name,
    pick,
)

UNAVAILABLE = (
    "Nmap", "Kerberoasting", "supply chain attack", "password spraying",
    "credential stuffing", "firmware implant", "living off the land",
    "DNS tunnelling", "golden ticket", "pass-the-hash",
)


def concept_scenarios(fragments, assignments, split, seed) -> list:
    generator = random.Random(seed + 11)
    entities = _entities(fragments)
    eligible = _eligible(entities)
    limit = {"train": 420, "validation": 55, "test": 55}[split]
    selected = generator.sample(eligible, min(limit, len(eligible)))
    records = []
    for entity, primary in selected:
        record = _concept(entity, primary, fragments, assignments, generator)
        if record is not None:
            records.append(record)
    records.extend(_defensive(eligible, fragments, assignments, split, generator))
    records.extend(_unavailable(fragments, assignments, split, generator))
    records.extend(_multiturn(eligible, fragments, assignments, split, generator))
    records.extend(_language(eligible, assignments, split, generator))
    return records


def conversation_scenarios(split) -> list:
    group = (f"conversation:{split}",)
    prefix = {"train": "", "validation": "Quick check: ", "test": "For a lab exercise, "}[split]
    records = []
    for query, reply in SOCIAL:
        records.append(compose(Scenario(
            task="social_conversation", query=_with_prefix(prefix, query),
            summary=reply, evidence=[], claims=[], entities=[], bindings={},
            route=Route.CAG_ONLY, intent="social",
        ), {}, extra_groups=group))
    for query, reply in CLARIFY:
        records.append(compose(Scenario(
            task="clarification", query=_with_prefix(prefix, query), summary=reply,
            evidence=[], claims=[], entities=[], bindings={},
            route=Route.CAG_ONLY, intent="clarification",
        ), {}, extra_groups=group))
    if split != "train":
        return records
    for query, reply in SOCIAL:
        records.append(compose(Scenario(
            task="social_conversation", query=f"Please, {query[0].lower() + query[1:]}",
            summary=reply, evidence=[], claims=[], entities=[], bindings={},
            route=Route.CAG_ONLY, intent="social",
        ), {}, extra_groups=group))
    return records


def _with_prefix(prefix: str, query: str) -> str:
    if not prefix:
        return query
    return prefix + query[0].lower() + query[1:]


def _entities(fragments):
    entities = defaultdict(list)
    for item in fragments:
        entities[item.entity_id].append(item)
    return entities


def _eligible(entities):
    result = []
    for entity, members in sorted(entities.items()):
        primary = next(
            (item for item in members
             if item.category in {"technique", "weakness", "vulnerability", "guidance"}),
            None,
        )
        if primary is not None and 3 <= len(display_name(primary)) <= 70:
            result.append((entity, primary))
    return result


def _with_companion(eligible, fragments):
    by_entity = defaultdict(list)
    for item in fragments:
        by_entity[item.entity_id].append(item)
    result = []
    for entity, primary in eligible:
        companion = next(
            (item for item in by_entity[entity]
             if item.category in {"mitigation", "remediation"}),
            None,
        )
        if companion is not None:
            result.append((entity, primary, companion))
    return result


def _distractor(primary, fragments, generator):
    pool = [
        item for item in fragments
        if item.category == primary.category and item.entity_id != primary.entity_id
        and primary.entity_id not in (item.title + item.content)
    ]
    if not pool:
        pool = [item for item in fragments if item.entity_id != primary.entity_id]
    if not pool:
        raise ValueError(f"No distractor record is available for {primary.entity_id}")
    return generator.choice(pool)


def _concept(entity, primary, fragments, assignments, generator) -> object | None:
    if not primary.entity_id.startswith(("T", "CWE-", "CAPEC-", "CVE-")):
        return None
    name = display_name(primary)
    evidence = evidence_for(primary)
    distractor = _distractor(primary, fragments, generator)
    decoy = evidence_for(distractor)
    query = pick(generator, CONCEPT, name=name)
    if generator.random() < 0.35:
        query = f"Explain {primary.title.split(' | ')[0].split(' - ')[0]} ({name})."
    scenario = Scenario(
        task="concept_definition", query=query,
        summary=(
            f"The supplied record describes {name}. It explains the documented behavior "
            "without establishing that it occurred in this environment."
        ),
        evidence=[evidence, decoy],
        claims=[factual(evidence), inference(
            "Documentation is not evidence of local occurrence or compromise."
        )],
        entities=[entity], bindings={evidence.id: primary.id, decoy.id: distractor.id},
        route=Route.CAG_RAG,
    )
    return compose(scenario, assignments, extra_groups=(assignments[primary.id],))


def _defensive(eligible, fragments, assignments, split, generator) -> list:
    candidates = _with_companion(eligible, fragments)
    limit = {"train": 360, "validation": 45, "test": 45}[split]
    selected = generator.sample(candidates, min(limit, len(candidates)))
    records = []
    for entity, primary, companion in selected:
        evidence = [evidence_for(primary), evidence_for(companion)]
        query = pick(generator, DEFENSIVE, name=display_name(primary))
        scenario = Scenario(
            task="defensive_guidance", query=query,
            summary=(
                f"The supplied documents describe {display_name(primary)} and a documented "
                "defensive action. Deployment in this environment is not established."
            ),
            evidence=evidence,
            claims=[factual(evidence[1]), factual(evidence[0]), inference(
                "The record does not establish that the control is deployed or effective here."
            )],
            entities=[entity],
            bindings={evidence[0].id: primary.id, evidence[1].id: companion.id},
            route=Route.CAG_RAG,
        )
        records.append(compose(scenario, assignments,
                               extra_groups=(assignments[primary.id],)))
    return records


def _unavailable(fragments, assignments, split, generator) -> list:
    text = " ".join(f"{item.title} {item.content}".casefold() for item in fragments)
    owner = {"train": 0, "validation": 1, "test": 2}[split]
    terms = [
        term for index, term in enumerate(UNAVAILABLE)
        if index % 3 == owner and term.casefold() not in text
    ]
    records = []
    for term in terms:
        for query in (f"What is {term}?", f"Explain {term}.",
                      f"How does {term} work?", f"Can you define {term}?"):
            fragment = generator.choice(fragments)
            decoy = evidence_for(fragment)
            scenario = Scenario(
                task="unavailable_concept", query=query,
                summary=(
                    f"{term} is a cybersecurity topic, but the supplied records do not define "
                    "it. I will not substitute an unrelated record."
                ),
                evidence=[decoy], claims=[unavailable(
                    f"No supplied record defines {term}; the available evidence is unrelated."
                )],
                entities=[term], bindings={decoy.id: fragment.id}, route=Route.CAG_RAG,
            )
            records.append(compose(scenario, assignments, extra_groups=(f"task:{split}",)))
    return records


def _multiturn(eligible, fragments, assignments, split, generator) -> list:
    candidates = _with_companion(eligible, fragments)
    limit = {"train": 320, "validation": 40, "test": 40}[split]
    selected = generator.sample(candidates, min(limit, len(candidates)))
    records = []
    for entity, primary, companion in selected:
        name = display_name(primary)
        evidence = [evidence_for(primary), evidence_for(companion)]
        conversation = [
            ConversationMessage(role="user", content=f"What is {name}?"),
            ConversationMessage(
                role="assistant",
                content=f"{name} is documented in the supplied record as a defensive topic.",
            ),
        ]
        query = "How do defenders mitigate it?"
        scenario = Scenario(
            task="multiturn_followup", query=query,
            summary=(
                f"The follow-up concerns {name}. The supplied record documents a defensive "
                "action; it does not establish local execution or deployment."
            ),
            evidence=evidence,
            claims=[factual(evidence[1]), inference(
                "The conversation does not add local telemetry or proof of compromise."
            )],
            entities=[entity],
            bindings={evidence[0].id: primary.id, evidence[1].id: companion.id},
            route=Route.CAG_RAG, conversation=conversation,
            resolved_query=f"How do defenders mitigate {name}?",
            subject=name, search_query=f"{name} mitigation",
        )
        records.append(compose(scenario, assignments,
                               extra_groups=(assignments[primary.id],)))
    return records


def _language(eligible, assignments, split, generator) -> list:
    limit = {"train": 320, "validation": 40, "test": 40}[split]
    selected = generator.sample(eligible, min(limit, len(eligible)))
    records = []
    languages = list(LANGUAGES)
    for entity, primary in selected:
        language = generator.choice(languages)
        name = display_name(primary)
        query = generator.choice(LANGUAGES[language]).format(name=name)
        evidence = evidence_for(primary)
        scenario = Scenario(
            task="language_variant", query=query,
            summary=(
                f"The supplied record describes {name}. The answer follows the configured "
                "English response language while quotations stay verbatim."
            ),
            evidence=[evidence], claims=[factual(evidence), inference(
                "The supplied documentation does not establish local occurrence."
            )],
            entities=[entity], bindings={evidence.id: primary.id},
            route=Route.CAG_RAG, resolved_query=f"What is {name}?",
            subject=name, search_query=name, language="English",
        )
        records.append(compose(scenario, assignments,
                               extra_groups=(assignments[primary.id],)))
    return records
