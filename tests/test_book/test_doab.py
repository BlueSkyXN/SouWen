from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.book.doab import DOABClient
from souwen.core.exceptions import NotFoundError
from souwen.search import search_books, search_by_capability

_OAI_DC = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
  xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:oaire="https://raw.githubusercontent.com/rcic/openaire4/master/schemas/4.0/oaire.xsd">
  <GetRecord><record><header>
    <identifier>oai:directory.doabooks.org:20.500.12854/1234</identifier>
  </header><metadata><oai_dc:dc>
    <dc:title>Climate Book</dc:title>
    <dc:creator>Ada Author</dc:creator>
    <dc:contributor>Bea Editor</dc:contributor>
    <dc:subject>Climate change</dc:subject>
    <dc:description>Published</dc:description>
    <dc:description>Open access climate scholarship.</dc:description>
    <dc:publisher>Open Press</dc:publisher>
    <dc:language>eng</dc:language>
    <dc:alternateIdentifier type="ISBN">978-1-2345-6789-0</dc:alternateIdentifier>
    <dc:alternateIdentifier type="DOI">https://doi.org/10.1234/example</dc:alternateIdentifier>
    <dc:identifier type="URL">https://directory.doabooks.org/handle/20.500.12854/1234</dc:identifier>
    <dc:identifier>https://publisher.example/books/climate</dc:identifier>
    <dc:identifier>https://doi.org/10.1234/example</dc:identifier>
    <oaire:licenseCondition uri="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</oaire:licenseCondition>
    <dc:rights>open access</dc:rights>
  </oai_dc:dc></metadata></record></GetRecord>
</OAI-PMH>"""

_LIST_RECORDS = _OAI_DC.replace("<GetRecord>", "<ListRecords>").replace(
    "</GetRecord>", "</ListRecords>"
)

_METS = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
  xmlns:mets="http://www.loc.gov/METS/" xmlns:xlink="http://www.w3.org/1999/xlink">
  <GetRecord><record><metadata><mets:mets><mets:fileSec><mets:fileGrp USE="ORIGINAL">
    <mets:file ID="file-1" MIMETYPE="application/pdf" SIZE="1234">
      <mets:FLocat xlink:href="https://directory.doabooks.org/bitstream/20.500.12854/1234/1/climate.pdf" />
    </mets:file>
  </mets:fileGrp></mets:fileSec></mets:mets></metadata></record></GetRecord>
</OAI-PMH>"""


async def test_search_uses_one_official_books_set_harvest_and_filters_metadata(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://directory\.doabooks\.org/oai/request.*"), text=_LIST_RECORDS
    )

    async with DOABClient() as client:
        response = await client.search("climate", per_page=2)

    request = httpx_mock.get_request()
    assert request is not None
    assert dict(request.url.params) == {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc",
        "set": "com_20.500.12854_5",
    }
    assert response.page == 1
    assert response.per_page == 2
    assert len(response.results) == 1
    book = response.results[0]
    assert book.source_record_id == "20.500.12854/1234"
    assert book.title == "Climate Book"
    assert [author.name for author in book.authors] == ["Ada Author"]
    assert [author.name for author in book.contributors] == ["Bea Editor"]
    assert book.publishers == ["Open Press"]
    assert book.subjects == ["Climate change"]
    assert book.languages == ["eng"]
    assert book.description == "Open access climate scholarship."
    assert book.access.status == "open_access"
    assert book.access.rights == "CC BY 4.0"
    assert book.access.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert [(identifier.scheme, identifier.value) for identifier in book.identifiers] == [
        ("source_record_id", "oai:directory.doabooks.org:20.500.12854/1234"),
        ("isbn13", "978-1-2345-6789-0"),
        ("doi", "10.1234/example"),
    ]
    assert [resource.relation for resource in book.resources] == [
        "catalog_record",
        "publisher_record",
        "doi",
    ]


async def test_detail_maps_mets_bitstream_without_requesting_it(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://directory\.doabooks\.org/oai/request.*metadataPrefix=oai_dc.*"),
        text=_OAI_DC,
    )
    httpx_mock.add_response(
        url=re.compile(r"https://directory\.doabooks\.org/oai/request.*metadataPrefix=mets.*"),
        text=_METS,
    )

    async with DOABClient() as client:
        book = await client.get_by_id("20.500.12854/1234", file_limit=1)

    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert (
        dict(requests[0].url.params)["identifier"] == "oai:directory.doabooks.org:20.500.12854/1234"
    )
    bitstream = book.resources[-1]
    assert (
        bitstream.relation,
        bitstream.file_name,
        bitstream.size_bytes,
        bitstream.media_type,
    ) == (
        "bitstream",
        "climate.pdf",
        1234,
        "application/pdf",
    )
    assert bitstream.url.endswith("/climate.pdf")
    assert bitstream.access.license_url == "https://creativecommons.org/licenses/by/4.0/"


@pytest.mark.parametrize(
    ("record_id", "file_limit"),
    [
        ("", 1),
        ("not-a-doab-id", 1),
        ("20.500.12854/1234?bad=true", 1),
        ("20.500.12854/1234", 0),
        ("20.500.12854/1234", 26),
    ],
)
async def test_detail_rejects_invalid_input_before_request(
    record_id: str, file_limit: int, httpx_mock: HTTPXMock
) -> None:
    async with DOABClient() as client:
        with pytest.raises(ValueError):
            await client.get_by_id(record_id, file_limit=file_limit)
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize(("per_page", "page"), [(0, 1), (26, 1), (1, 2)])
async def test_search_rejects_unbounded_or_unsupported_pagination_before_request(
    per_page: int, page: int, httpx_mock: HTTPXMock
) -> None:
    async with DOABClient() as client:
        with pytest.raises(ValueError):
            await client.search("climate", per_page=per_page, page=page)
    assert httpx_mock.get_requests() == []


async def test_oai_missing_record_maps_to_not_found(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://directory\.doabooks\.org/oai/request.*"),
        text="""<OAI-PMH><error code="idDoesNotExist">unknown identifier</error></OAI-PMH>""",
    )
    async with DOABClient() as client:
        with pytest.raises(NotFoundError):
            await client.get_by_id("20.500.12854/9999")


async def test_registry_dispatches_explicit_doab_search(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(self: DOABClient, query: str, *, per_page: int, page: int = 1):
        assert (query, per_page, page) == ("climate", 2, 1)
        return type("Response", (), {"query": query, "source": "doab", "results": []})()

    monkeypatch.setattr(DOABClient, "search", fake_search)
    responses = await search_books("climate", sources=["doab"], per_page=2)

    assert len(responses) == 1
    assert responses[0].source == "doab"


async def test_registry_dispatches_doab_detail_by_handle(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = type("Detail", (), {"source": "doab"})()

    async def fake_detail(self: DOABClient, record_id: str, *, file_limit: int = 10):
        assert (record_id, file_limit) == ("20.500.12854/1234", 10)
        return expected

    monkeypatch.setattr(DOABClient, "get_by_id", fake_detail)
    results = await search_by_capability("20.500.12854/1234", "get_detail", sources=["doab"])

    assert results == [expected]
