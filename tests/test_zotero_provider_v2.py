from __future__ import annotations

import pytest

from souwen.providers.runtime_clients.models import SearchResponse
from souwen.providers.runtime_clients.paper.zotero import ZoteroClient
from souwen.platform.provider_spi import ExecutionContext, RequestContext, SearchRequest
from souwen.providers.information_sources.zotero import (
    ZOTERO_PROVIDER_MANIFEST,
    ZOTERO_PROVIDER_SPEC,
    ZoteroSearchProvider,
)


class _Client:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response

    async def search(self, *_args, **_kwargs) -> SearchResponse:
        return self.response


def test_zotero_provider_v2_declares_key_and_non_secret_library_configuration() -> None:
    assert ZOTERO_PROVIDER_SPEC.auth.reference == "ZOTERO_API_KEY"
    assert ZOTERO_PROVIDER_SPEC.configuration_keys == ("enabled", "library_id", "library_type")
    assert ZOTERO_PROVIDER_MANIFEST.secrets.references == ("ZOTERO_API_KEY",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("publisher_url", "doi", "library_type", "expected_url"),
    (
        (
            "https://publisher.example/article",
            "",
            "User",
            "https://api.zotero.org/users/12345/items/ABCD1234",
        ),
        (
            "",
            "10.1000/zotero-b2",
            "user",
            "https://api.zotero.org/users/12345/items/ABCD1234",
        ),
        ("", "", "Group", "https://api.zotero.org/groups/12345/items/ABCD1234"),
    ),
)
async def test_zotero_identity_does_not_depend_on_optional_external_url(
    publisher_url: str,
    doi: str,
    library_type: str,
    expected_url: str,
) -> None:
    client = ZoteroClient(
        api_key="fixture-zotero-key",
        library_id="12345",
        library_type=library_type,
    )
    paper = client._parse_item(
        {
            "key": "ABCD1234",
            "data": {
                "itemType": "journalArticle",
                "title": "Zotero record",
                "creators": [],
                "url": publisher_url,
                "DOI": doi,
            },
        }
    )
    page = await ZoteroSearchProvider(
        _Client(
            SearchResponse(
                query="zotero",
                source="zotero",
                total_results=1,
                page=1,
                per_page=10,
                results=[paper],
            )
        )
    ).search(
        SearchRequest(query="zotero", domains=("paper",)),
        RequestContext(request_id="zotero-url"),
        ExecutionContext.with_timeout(5),
    )
    await client._client.close()

    assert page.items[0].id == "zotero:ABCD1234"
    assert str(page.items[0].url) == expected_url
