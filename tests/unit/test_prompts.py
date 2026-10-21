from vera.domain.enums import Route
from vera.domain.reports import StreamStatistics
from vera.domain.requests import AnalysisRequest
from vera.providers.prompts import generation_prompt


def test_retry_prompt_distinguishes_titles_from_cited_content() -> None:
    prompt = generation_prompt(
        AnalysisRequest(query="Explain CWE-89"),
        Route.CAG_RAG,
        [],
        [],
        StreamStatistics(),
        ["Claim 0: supporting quote covers only 33% of meaningful claim terms"],
    )

    assert "Do not use evidence titles as claim text" in prompt
    assert "copy one short sentence" in prompt
