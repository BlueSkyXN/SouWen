from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import SearchResponse
from souwen.providers.runtime_clients.paper.openaire import OpenAireClient
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.openaire import (
    OPENAIRE_PROVIDER_MANIFEST,
    OPENAIRE_PROVIDER_SPEC,
    OpenAireSearchProvider,
)


class _Client:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response

    async def search(self, *_args, **_kwargs) -> SearchResponse:
        return self.response


def test_openaire_provider_v2_declares_optional_bearer_secret() -> None:
    assert OPENAIRE_PROVIDER_SPEC.auth.reference == "OPENAIRE_API_KEY"
    assert OPENAIRE_PROVIDER_SPEC.auth.required is False
    assert OPENAIRE_PROVIDER_MANIFEST.secrets.optional_references == ("OPENAIRE_API_KEY",)


@pytest.mark.asyncio
async def test_openaire_pdf_result_without_doi_keeps_stable_openaire_identity() -> None:
    paper = OpenAireClient._parse_result(
        {
            "header": {"dri:objIdentifier": "openaire:stable-b2"},
            "metadata": {
                "oaf:entity": {
                    "oaf:result": {
                        "title": {"$": "Repository result", "@classid": "main title"},
                        "children": {
                            "instance": [
                                {
                                    "webresource": [
                                        {"url": {"$": "https://repository.example/paper.pdf"}}
                                    ]
                                }
                            ]
                        },
                    }
                }
            },
        }
    )
    assert paper.source_url == "https://repository.example/paper.pdf"
    assert paper.raw["openaire_id"] == "openaire:stable-b2"

    page = await OpenAireSearchProvider(
        _Client(
            SearchResponse(
                query="repository",
                source="openaire",
                total_results=1,
                page=1,
                per_page=10,
                results=[paper],
            )
        )
    ).search(
        SearchRequest(query="repository", domains=("paper",)),
        RequestContext(request_id="openaire-pdf"),
        ExecutionContext.with_timeout(5),
    )

    assert page.items[0].id == "openaire:openaire:stable-b2"
    assert str(page.items[0].url) == (
        "https://explore.openaire.eu/search/publication?pid=openaire:stable-b2"
    )
