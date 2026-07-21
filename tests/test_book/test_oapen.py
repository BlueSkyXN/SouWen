from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.book.oapen import OAPENClient
from souwen.core.exceptions import NotFoundError
from souwen.search import search_books, search_by_capability

_DC = """<OAI-PMH xmlns="urn:oai" xmlns:dc="urn:dc" xmlns:oai_dc="urn:oai_dc" xmlns:oaire="urn:oaire">
<GetRecord><record><header><identifier>oai:library.oapen.org:20.500.12657/1234</identifier></header>
<metadata><oai_dc:dc><dc:title>Open Climate Book</dc:title><dc:creator>Ada Author</dc:creator><dc:contributor>Bea Editor</dc:contributor><dc:subject>Climate</dc:subject><dc:description>Published</dc:description><dc:description>Climate research.</dc:description><dc:language>eng</dc:language><dc:publisher>OAPEN Press</dc:publisher><dc:alternateIdentifier type="ISBN">9781234567890</dc:alternateIdentifier><dc:alternateIdentifier type="DOI">10.1234/oapen</dc:alternateIdentifier><dc:identifier type="URL">https://library.oapen.org/handle/20.500.12657/1234</dc:identifier><dc:identifier>https://publisher.example/book</dc:identifier><oaire:licenseCondition uri="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</oaire:licenseCondition><dc:rights>info:eu-repo/semantics/openAccess</dc:rights><oaire:fundingReference><oaire:funderName>Open Fund</oaire:funderName></oaire:fundingReference></oai_dc:dc></metadata></record></GetRecord></OAI-PMH>"""
_LIST = _DC.replace("<GetRecord>", "<ListRecords>").replace("</GetRecord>", "</ListRecords>")
_METS = """<OAI-PMH xmlns:mets="urn:mets" xmlns:xlink="http://www.w3.org/1999/xlink"><GetRecord><record><metadata><mets:mets><mets:fileSec><mets:file MIMETYPE="application/pdf" SIZE="42"><mets:FLocat xlink:href="https://library.oapen.org/bitstream/20.500.12657/1234/1/book.pdf"/></mets:file></mets:fileSec></mets:mets></metadata></record></GetRecord></OAI-PMH>"""


async def test_search_parses_oapen_book_metadata_and_funding(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://library\.oapen\.org/oai/request.*"), text=_LIST
    )
    async with OAPENClient() as client:
        response = await client.search("climate", per_page=1)
    request = httpx_mock.get_request()
    assert request and dict(request.url.params) == {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc",
        "set": "com_20.500.12657_5",
    }
    book = response.results[0]
    assert book.source_record_id == "20.500.12657/1234"
    assert [author.name for author in book.authors] == ["Ada Author"]
    assert [author.name for author in book.contributors] == ["Bea Editor"]
    assert book.funding == ["Open Fund"]
    assert book.access.status == "open_access"
    assert book.access.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert [(item.scheme, item.value) for item in book.identifiers] == [
        ("source_record_id", "oai:library.oapen.org:20.500.12657/1234"),
        ("isbn13", "9781234567890"),
        ("doi", "10.1234/oapen"),
    ]


async def test_detail_maps_declared_mets_bitstream_without_fetching_it(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://library\.oapen\.org/oai/request.*metadataPrefix=oai_dc.*"),
        text=_DC,
    )
    httpx_mock.add_response(
        url=re.compile(r"https://library\.oapen\.org/oai/request.*metadataPrefix=mets.*"),
        text=_METS,
    )
    async with OAPENClient() as client:
        book = await client.get_by_id("20.500.12657/1234", file_limit=1)
    assert len(httpx_mock.get_requests()) == 2
    bitstream = book.resources[-1]
    assert (
        bitstream.relation,
        bitstream.file_name,
        bitstream.size_bytes,
        bitstream.media_type,
    ) == ("bitstream", "book.pdf", 42, "application/pdf")


@pytest.mark.parametrize(
    ("record_id", "file_limit"), [("bad", 1), ("20.500.12657/1234", 0), ("20.500.12657/1234", 26)]
)
async def test_detail_rejects_invalid_input_before_request(
    record_id: str, file_limit: int, httpx_mock: HTTPXMock
) -> None:
    async with OAPENClient() as client:
        with pytest.raises(ValueError):
            await client.get_by_id(record_id, file_limit=file_limit)
    assert httpx_mock.get_requests() == []


async def test_oai_missing_record_maps_to_not_found(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://library\.oapen\.org/oai/request.*"),
        text='<OAI-PMH><error code="idDoesNotExist">unknown</error></OAI-PMH>',
    )
    async with OAPENClient() as client:
        with pytest.raises(NotFoundError):
            await client.get_by_id("20.500.12657/9999")


async def test_registry_dispatches_explicit_oapen_search_and_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(self: OAPENClient, query: str, *, per_page: int, page: int = 1):
        assert (query, per_page, page) == ("climate", 2, 1)
        return type("Response", (), {"source": "oapen", "results": []})()

    async def fake_detail(self: OAPENClient, record_id: str, *, file_limit: int = 10):
        assert (record_id, file_limit) == ("20.500.12657/1234", 10)
        return type("Detail", (), {"source": "oapen"})()

    monkeypatch.setattr(OAPENClient, "search", fake_search)
    monkeypatch.setattr(OAPENClient, "get_by_id", fake_detail)
    assert (await search_books("climate", sources=["oapen"], per_page=2))[0].source == "oapen"
    assert (await search_by_capability("20.500.12657/1234", "get_detail", sources=["oapen"]))[
        0
    ].source == "oapen"
