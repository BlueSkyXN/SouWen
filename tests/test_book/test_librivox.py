from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.book.librivox import LibriVoxClient
from souwen.core.exceptions import NotFoundError, ParseError, SourceUnavailableError
from souwen.models import BookResult
from souwen.search import search_books, search_by_capability

_SEARCH_BOOK = {
    "id": "253",
    "title": "Pride and Prejudice",
    "authors": [{"first_name": "Jane", "last_name": "Austen"}],
    "language": "English",
    "description": "metadata",
    "copyright_year": "1813",
    "url_librivox": "https://librivox.org/pride-and-prejudice/",
    "url_rss": "https://librivox.org/rss/253",
    "url_iarchive": "https://archive.org/details/pride",
    "url_zip_file": "https://archive.org/download/pride.zip",
}

_DETAIL_BOOK = {
    **_SEARCH_BOOK,
    "sections": [
        {
            "id": "1",
            "section_number": "1",
            "title": "Chapter 1",
            "listen_url": "https://archive.org/download/pride/chapter-1.mp3",
            "file_name": "chapter-1.mp3",
            "playtime": "123",
            "readers": [{"reader_id": "10", "display_name": "Reader One"}],
        },
        {
            "id": "2",
            "section_number": "2",
            "title": "Chapter 2",
            "listen_url": "https://archive.org/download/pride/chapter-2.mp3",
            "readers": [
                {"reader_id": "10", "display_name": "Reader One"},
                {"reader_id": "11", "display_name": "Reader Two"},
            ],
        },
        {
            "id": "3",
            "section_number": "3",
            "title": "Unlinked section",
            "playtime": "0",
            "readers": [{"reader_id": "12", "display_name": "Reader Three"}],
        },
    ],
}


async def test_search_maps_catalog_metadata_without_section_audio_requests(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://librivox\.org/api/feed/audiobooks/.*"),
        json={"books": [_SEARCH_BOOK]},
    )

    async with LibriVoxClient() as client:
        response = await client.search("pride", per_page=2, page=2)

    request = httpx_mock.get_request()
    assert request and dict(request.url.params) == {
        "title": "pride",
        "format": "json",
        "limit": "2",
        "offset": "2",
    }
    book = response.results[0]
    assert [author.name for author in book.authors] == ["Jane Austen"]
    assert book.readers == []
    assert book.copyright_year == 1813
    assert book.audio_sections == []
    assert [(resource.relation, resource.format) for resource in book.resources] == [
        ("catalog_record", None),
        ("rss", "RSS"),
        ("external_catalog_record", None),
        ("audio_archive", "ZIP"),
    ]
    assert book.access.status == "unknown"
    assert book.access.machine_download is None


async def test_detail_maps_bounded_audio_sections_readers_and_format(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://librivox\.org/api/feed/audiobooks/.*"),
        json={"books": [_DETAIL_BOOK]},
    )

    async with LibriVoxClient() as client:
        book = await client.get_by_id("253", audio_limit=2)

    request = httpx_mock.get_request()
    assert request and dict(request.url.params) == {"id": "253", "format": "json", "extended": "1"}
    assert [
        (section.source_section_id, section.section_number) for section in book.audio_sections
    ] == [
        ("1", 1),
        ("2", 2),
    ]
    assert [reader.name for reader in book.readers] == ["Reader One", "Reader Two"]
    first_audio = book.audio_sections[0].resource
    assert first_audio is not None
    assert (first_audio.relation, first_audio.media_type, first_audio.format) == (
        "audio",
        "audio/mpeg",
        "MP3",
    )
    assert first_audio.file_name == "chapter-1.mp3"
    assert [resource.relation for resource in book.resources][-2:] == ["audio", "audio"]
    assert all(resource.access.status == "unknown" for resource in book.resources)


async def test_search_supports_official_author_filter(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://librivox\.org/api/feed/audiobooks/.*"),
        json={"books": [_SEARCH_BOOK]},
    )

    async with LibriVoxClient() as client:
        response = await client.search("austen", search_field="author")

    request = httpx_mock.get_request()
    assert request and dict(request.url.params) == {
        "author": "austen",
        "format": "json",
        "limit": "10",
        "offset": "0",
    }
    assert response.results[0].source_record_id == "253"


async def test_detail_preserves_missing_audio_link_and_reader_metadata(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://librivox\.org/api/feed/audiobooks/.*"),
        json={"books": [_DETAIL_BOOK]},
    )

    async with LibriVoxClient() as client:
        book = await client.get_by_id("253", audio_limit=3)

    missing_link = book.audio_sections[-1]
    assert missing_link.source_section_id == "3"
    assert missing_link.resource is None
    assert missing_link.duration_seconds == 0
    assert [reader.name for reader in missing_link.readers] == ["Reader Three"]
    assert [reader.name for reader in book.readers] == ["Reader One", "Reader Two", "Reader Three"]


@pytest.mark.parametrize("per_page,page", [(0, 1), (51, 1), (1, 0)])
async def test_search_rejects_invalid_pagination_before_request(
    per_page: int, page: int, httpx_mock: HTTPXMock
) -> None:
    async with LibriVoxClient() as client:
        with pytest.raises(ValueError):
            await client.search("pride", per_page=per_page, page=page)
    assert httpx_mock.get_requests() == []


async def test_search_rejects_unsupported_search_field_before_request(
    httpx_mock: HTTPXMock,
) -> None:
    async with LibriVoxClient() as client:
        with pytest.raises(ValueError):
            await client.search("pride", search_field="genre")  # type: ignore[arg-type]
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("value", ["", "bad", "12/x"])
async def test_invalid_id_rejected_before_request(value: str, httpx_mock: HTTPXMock) -> None:
    async with LibriVoxClient() as client:
        with pytest.raises(ValueError):
            await client.get_by_id(value)
    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("audio_limit", [0, 51])
async def test_invalid_audio_limit_rejected_before_request(
    audio_limit: int, httpx_mock: HTTPXMock
) -> None:
    async with LibriVoxClient() as client:
        with pytest.raises(ValueError):
            await client.get_by_id("253", audio_limit=audio_limit)
    assert httpx_mock.get_requests() == []


async def test_detail_missing_malformed_and_5xx_errors(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://librivox.org/api/feed/audiobooks/?id=253&format=json&extended=1",
        json={"books": []},
    )
    async with LibriVoxClient() as client:
        with pytest.raises(NotFoundError):
            await client.get_by_id("253")

    httpx_mock.add_response(
        url=re.compile(r"https://librivox\.org/api/feed/audiobooks/.*"), json={"unexpected": []}
    )
    async with LibriVoxClient() as client:
        with pytest.raises(ParseError):
            await client.search("x")

    httpx_mock.add_response(
        url=re.compile(r"https://librivox\.org/api/feed/audiobooks/.*"), status_code=503
    )
    async with LibriVoxClient() as client:
        with pytest.raises(SourceUnavailableError):
            await client.search("x")


async def test_registry_dispatches_explicit_librivox_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(self: LibriVoxClient, query: str, *, per_page: int, page: int = 1):
        assert (query, per_page, page) == ("audiobook", 2, 1)
        return type("Response", (), {"query": query, "source": "librivox", "results": []})()

    monkeypatch.setattr(LibriVoxClient, "search", fake_search)
    responses = await search_books("audiobook", sources=["librivox"], per_page=2)

    assert len(responses) == 1
    assert responses[0].source == "librivox"


async def test_registry_dispatches_librivox_detail_by_numeric_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = BookResult(
        source="librivox",
        source_record_id="253",
        title="Detail",
        source_url="https://librivox.org/pride-and-prejudice/",
    )

    async def fake_detail(self: LibriVoxClient, audiobook_id: str, *, audio_limit: int = 50):
        assert (audiobook_id, audio_limit) == ("253", 50)
        return expected

    monkeypatch.setattr(LibriVoxClient, "get_by_id", fake_detail)
    results = await search_by_capability("253", "get_detail", sources=["librivox"])

    assert results == [expected]
