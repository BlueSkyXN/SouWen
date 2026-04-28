"""Tests for souwen.llm.prompts — pure function tests."""

from souwen.llm.models import SummaryCitation
from souwen.llm.prompts import (
    SYSTEM_PROMPT_ACADEMIC,
    SYSTEM_PROMPT_BRIEF,
    SYSTEM_PROMPT_DETAILED,
    format_results_for_llm,
    get_system_prompt,
)
from souwen.models import (
    Applicant,
    Author,
    PaperResult,
    PatentResult,
    SearchResponse,
    SourceType,
    WebSearchResult,
)


def _paper(
    title: str = "Test Paper",
    *,
    doi: str | None = "10.1234/test",
    source_url: str = "https://example.com/paper1",
    abstract: str = "This is a test abstract",
) -> PaperResult:
    return PaperResult(
        source=SourceType.OPENALEX,
        title=title,
        authors=[Author(name="John Doe")],
        abstract=abstract,
        doi=doi,
        year=2024,
        venue="Test Journal",
        source_url=source_url,
    )


def _patent(title: str = "Test Patent", patent_id: str = "US123") -> PatentResult:
    return PatentResult(
        source=SourceType.PATENTSVIEW,
        title=title,
        patent_id=patent_id,
        applicants=[Applicant(name="Acme Corp")],
        inventors=["Jane Inventor"],
        publication_date="2024-01-02",
        abstract="A useful test invention",
        source_url=f"https://example.com/patent/{patent_id}",
    )


def _web(title: str = "Test Web", url: str = "https://example.com/web") -> WebSearchResult:
    return WebSearchResult(
        source=SourceType.WEB_DUCKDUCKGO,
        title=title,
        url=url,
        snippet="A web snippet",
        engine="duckduckgo",
    )


def _response(source: SourceType, results: list) -> SearchResponse:
    return SearchResponse(source=source, query="test", total_results=len(results), results=results)


def test_get_system_prompt_brief():
    assert get_system_prompt("brief") == SYSTEM_PROMPT_BRIEF
    assert "Mode: Brief summary" in get_system_prompt("brief")


def test_get_system_prompt_detailed():
    assert get_system_prompt("detailed") == SYSTEM_PROMPT_DETAILED
    assert "Mode: Detailed summary" in get_system_prompt("detailed")


def test_get_system_prompt_academic():
    assert get_system_prompt("academic") == SYSTEM_PROMPT_ACADEMIC
    assert "Mode: Academic summary" in get_system_prompt("academic")


def test_get_system_prompt_unknown_mode():
    assert get_system_prompt("unknown") == SYSTEM_PROMPT_BRIEF


def test_get_system_prompt_override():
    assert get_system_prompt("brief", "custom prompt") == "custom prompt"


def test_format_results_for_llm_papers():
    text, citations = format_results_for_llm([_response(SourceType.OPENALEX, [_paper()])])

    assert "[1] | Title: Test Paper" in text
    assert "Authors: John Doe" in text
    assert "Venue: Test Journal" in text
    assert "Year: 2024" in text
    assert "Abstract: This is a test abstract" in text
    assert citations == [
        SummaryCitation(
            id=1,
            title="Test Paper",
            url="https://example.com/paper1",
            source="openalex",
        )
    ]


def test_format_results_for_llm_patents():
    text, citations = format_results_for_llm([_response(SourceType.PATENTSVIEW, [_patent()])])

    assert "[1] | Title: Test Patent" in text
    assert "ID: US123" in text
    assert "Applicants: Acme Corp" in text
    assert "Date: 2024-01-02" in text
    assert citations[0].title == "Test Patent"
    assert citations[0].url == "https://example.com/patent/US123"
    assert citations[0].source == "patentsview"


def test_format_results_for_llm_web():
    text, citations = format_results_for_llm([_response(SourceType.WEB_DUCKDUCKGO, [_web()])])

    assert "[1] | Title: Test Web" in text
    assert "Snippet: A web snippet" in text
    assert "URL: https://example.com/web" in text
    assert citations[0].title == "Test Web"
    assert citations[0].url == "https://example.com/web"
    assert citations[0].source == "web_duckduckgo"


def test_format_results_for_llm_dedup():
    duplicate = _paper("Duplicate Paper", doi="10.1234/TEST", source_url="https://example.com/paper2")

    text, citations = format_results_for_llm([_response(SourceType.OPENALEX, [_paper(), duplicate])])

    assert "Test Paper" in text
    assert "Duplicate Paper" not in text
    assert len(citations) == 1


def test_format_results_for_llm_max_results():
    papers = [
        _paper(f"Paper {idx}", doi=f"10.1234/{idx}", source_url=f"https://example.com/{idx}")
        for idx in range(5)
    ]

    text, citations = format_results_for_llm([_response(SourceType.OPENALEX, papers)], max_results=3)

    assert len(citations) == 3
    assert "Paper 0" in text
    assert "Paper 2" in text
    assert "Paper 3" not in text


def test_format_results_for_llm_empty():
    text, citations = format_results_for_llm([_response(SourceType.OPENALEX, [])])

    assert text == ""
    assert citations == []


def test_format_results_for_llm_mixed():
    responses = [
        _response(SourceType.OPENALEX, [_paper()]),
        _response(SourceType.PATENTSVIEW, [_patent()]),
        _response(SourceType.WEB_DUCKDUCKGO, [_web()]),
    ]

    text, citations = format_results_for_llm(responses)

    assert "[1] | Title: Test Paper" in text
    assert "[2] | Title: Test Patent" in text
    assert "[3] | Title: Test Web" in text
    assert [citation.id for citation in citations] == [1, 2, 3]
    assert [citation.source for citation in citations] == [
        "openalex",
        "patentsview",
        "web_duckduckgo",
    ]
