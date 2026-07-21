from __future__ import annotations

import pytest

from souwen.core.exceptions import SourceUnavailableError
from souwen.models import CitationCountResponse, CitationGraphResponse


async def test_public_facades_use_explicit_opencitations_capabilities(
    monkeypatch: pytest.MonkeyPatch,
):
    import souwen.citations as citations

    seen = []

    async def fake_search(query, capability, sources, **kwargs):
        seen.append((query, capability, sources, kwargs))
        if capability.endswith("citation_count"):
            return [
                CitationCountResponse(
                    identifier={"scheme": "doi", "value": "10.1/x"},
                    count=2,
                    source_url="https://example.test/count",
                )
            ]
        return [
            CitationGraphResponse(
                identifier={"scheme": "doi", "value": "10.1/x"},
                relation="citations",
                total_edges=0,
                returned_edges=0,
                source_url="https://example.test/graph",
            )
        ]

    monkeypatch.setattr(citations, "search_by_capability", fake_search)
    assert (await citations.get_citation_count("doi:10.1/x")).count == 2
    assert (await citations.get_incoming_citations("doi:10.1/x", max_edges=3)).returned_edges == 0
    assert seen == [
        (
            "doi:10.1/x",
            "opencitations:citation_count",
            ["opencitations"],
            {"identifier": "doi:10.1/x"},
        ),
        (
            "doi:10.1/x",
            "opencitations:citations",
            ["opencitations"],
            {"identifier": "doi:10.1/x", "max_edges": 3},
        ),
    ]


async def test_public_facade_does_not_turn_unavailable_source_into_empty_graph(
    monkeypatch: pytest.MonkeyPatch,
):
    import souwen.citations as citations

    async def fake_search(*_args, **_kwargs):
        return []

    monkeypatch.setattr(citations, "search_by_capability", fake_search)
    with pytest.raises(SourceUnavailableError):
        await citations.get_references("doi:10.1/x")
