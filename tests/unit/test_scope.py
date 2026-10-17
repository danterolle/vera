from vera.domain.reports import GeneratedAnswer


def test_declared_out_of_scope_discards_unrelated_claims() -> None:
    draft = GeneratedAnswer.model_validate({
        "summary": "Here is a recipe.",
        "claims": [{"text": "Use pasta", "status": "system_inference"}],
        "out_of_scope": True,
    })
    assert draft.claims == []
    assert draft.summary == "VERA answers only cybersecurity questions."


def test_cybersecurity_answers_keep_their_claims() -> None:
    draft = GeneratedAnswer.model_validate({
        "summary": "Evidence is missing for this CVE.",
        "claims": [{"text": "No information available", "status": "unavailable"}],
        "out_of_scope": False,
    })
    assert len(draft.claims) == 1
    assert draft.out_of_scope is False
