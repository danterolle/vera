import random
from dataclasses import dataclass, field

from vera.domain.enums import ClaimStatus, Route
from vera.domain.evidence import Citation, Claim, Evidence, make_evidence
from vera.domain.plans import ResourcePlan
from vera.domain.reports import DetectionAlert, GeneratedAnswer, StreamStatistics
from vera.domain.requests import AnalysisRequest, ConversationMessage
from vera.providers.prompts import SYSTEM_PROMPT, generation_prompt
from vera.reasoning.validation import validate_and_repair
from vera_domain.models import (
    ScenarioMetadata,
    SourceFragment,
    TrainingRecord,
    fingerprint,
)


@dataclass
class Scenario:
    task: str
    query: str
    summary: str
    evidence: list[Evidence]
    claims: list[Claim]
    entities: list[str]
    bindings: dict[str, str]
    route: Route = Route.CAG_RAG
    feedback: list[str] = field(default_factory=list)
    out_of_scope: bool = False
    intent: str = "cybersecurity"
    resolved_query: str | None = None
    subject: str | None = None
    search_query: str | None = None
    conversation: list[ConversationMessage] = field(default_factory=list)
    language: str = "English"


def evidence_for(fragment: SourceFragment) -> Evidence:
    bundled = fragment.snapshot == "bundled-corpus"
    title = fragment.title if bundled else f"{fragment.title} | snapshot {fragment.revision[:10]}"
    item = make_evidence(
        fragment.source,
        title[:300],
        fragment.content,
        url=fragment.source_url or None,
        metadata={
            "provenance": (
                "bundled_official_snapshot" if bundled else "pinned_public_snapshot"
            ),
            "lookup_method": "corpus" if bundled else "pinned_snapshot",
        },
    )
    return item.model_copy(update={"id": f"ev-domain-{fragment.id[4:20]}"})


def short_quote(text: str, maximum: int = 360) -> str:
    stripped = text.strip()
    if len(stripped) <= maximum:
        return stripped
    limit = stripped[:maximum]
    for separator in (". ", "? ", "! "):
        index = limit.rfind(separator)
        if index >= 40:
            return stripped[: index + 1]
    index = limit.rfind(" ")
    return stripped[:index].strip() if index > 40 else limit


def factual(evidence: Evidence, quote: str | None = None) -> Claim:
    selected = quote or short_quote(evidence.content)
    if selected not in evidence.content:
        raise ValueError("A factual quote must be an exact substring of the evidence")
    return Claim(
        text=selected, status=ClaimStatus.SUPPORTED_FACT, evidence_ids=[evidence.id],
        citations=[Citation(evidence_id=evidence.id, supporting_quote=selected)],
    )


def inference(text: str) -> Claim:
    return Claim(text=text, status=ClaimStatus.SYSTEM_INFERENCE)


def unavailable(text: str, evidence: Evidence | None = None) -> Claim:
    return Claim(
        text=text, status=ClaimStatus.UNAVAILABLE,
        evidence_ids=[evidence.id] if evidence is not None else [],
        citations=[],
    )


def simulated(alert: DetectionAlert, evidence: Evidence) -> Claim:
    return Claim(
        text=alert.description, status=ClaimStatus.SIMULATED,
        evidence_ids=[evidence.id],
        citations=[Citation(evidence_id=evidence.id, supporting_quote=evidence.content)],
    )


def compose(
    scenario: Scenario, assignments: dict[str, str], *,
    alerts: list[DetectionAlert] | None = None,
    statistics: StreamStatistics | None = None,
    detector_family: str | None = None,
    window_case: str | None = None,
    event_replay_id: str | None = None,
    extra_groups: tuple[str, ...] = (),
) -> TrainingRecord:
    evidence = list(scenario.evidence)
    random.Random(fingerprint(scenario.query)).shuffle(evidence)
    plan = ResourcePlan(
        use_cag=True,
        use_rag=scenario.route in {Route.CAG_RAG, Route.CAG_RAG_TOOL, Route.FULL},
        use_tools=scenario.route in {Route.CAG_RAG_TOOL, Route.FULL},
        use_stream=scenario.route in {Route.STREAM, Route.FULL},
        intent=scenario.intent,
        resolved_query=(scenario.resolved_query or scenario.query)[:1000],
        subject=(scenario.subject or "")[:160],
        search_query=(scenario.search_query or scenario.query)[:300],
    )
    request = AnalysisRequest(query=scenario.query, conversation=scenario.conversation)
    prompt = generation_prompt(
        request, scenario.route, evidence, alerts or [], statistics or StreamStatistics(),
        scenario.feedback, response_language=scenario.language, plan=plan,
    )
    answer = GeneratedAnswer(
        summary=scenario.summary, claims=scenario.claims,
        out_of_scope=scenario.out_of_scope,
    )
    _validate_answer(answer, evidence)
    source_ids = sorted(set(scenario.bindings.values()))
    groups = sorted(
        {assignments[source] for source in source_ids if source in assignments}
        | set(extra_groups)
    )
    if not groups:
        raise ValueError(f"{scenario.task} needs at least one split group")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": answer.model_dump_json()},
    ]
    rebuilt = generation_prompt(
        request, scenario.route, evidence, alerts or [], statistics or StreamStatistics(),
        scenario.feedback, response_language=scenario.language, plan=plan,
    )
    if rebuilt != prompt:
        raise ValueError("The composed prompt is not reproducible from runtime inputs")
    return _record(scenario, messages, source_ids, groups, alerts, detector_family,
                   window_case, event_replay_id)


def _validate_answer(answer: GeneratedAnswer, evidence: list[Evidence]) -> None:
    if answer.out_of_scope and answer.claims:
        raise ValueError("Out-of-scope answers cannot contain claims")
    if len(answer.claims) > 6:
        raise ValueError("The answer exceeds the six-claim contract")
    outcome = validate_and_repair(answer, evidence, repair=False)
    if outcome.errors:
        raise ValueError("; ".join(outcome.errors))
    by_id = {item.id: item for item in evidence}
    for claim in answer.claims:
        for citation in claim.citations:
            if citation.supporting_quote not in by_id[citation.evidence_id].content:
                raise ValueError("A supporting quote is not verbatim")
        if (
            claim.status == ClaimStatus.SUPPORTED_FACT
            and claim.text != claim.citations[0].supporting_quote
        ):
            raise ValueError("A supported fact must equal its quotation")


def _record(scenario, messages, source_ids, groups, alerts, detector_family,
            window_case, event_replay_id) -> TrainingRecord:
    identity = fingerprint(messages)
    metadata = ScenarioMetadata(
        family=scenario.task,
        entities=sorted(set(scenario.entities)),
        source_bindings=dict(scenario.bindings),
        detector_family=detector_family,
        window_case=window_case,
        feedback_kind="synthetic_analyst_feedback" if scenario.feedback else None,
        event_replay_id=event_replay_id,
        alert_count=len(alerts or []),
        conversation_turns=len(scenario.conversation),
        language=scenario.language,
        intent=scenario.intent,
    )
    return TrainingRecord(
        id=f"row-{identity[:24]}", task=scenario.task, groups=groups,
        source_ids=source_ids, scenario=metadata,
        messages=[{"role": item["role"], "content": item["content"]} for item in messages],
    )
