from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from souwen.book.wikisource import WikisourceClient
from souwen.core.exceptions import NotFoundError, SourceUnavailableError
from souwen.models import WikisourcePage
from souwen.search import search_books, search_by_capability
from souwen.wikisource import get_wikisource_page_detail


def _page(
    *,
    page_id: int = 123,
    title: str = "測試頁",
    revision_id: int = 456,
    size: int = 24,
    content: str | None = None,
) -> dict[str, object]:
    revision: dict[str, object] = {
        "revid": revision_id,
        "parentid": revision_id - 1,
        "timestamp": "2024-01-02T03:04:05Z",
        "size": size,
        "contentmodel": "wikitext",
        "user": "Example editor",
        "comment": "fixture revision",
        "sha1": "a" * 40,
        "slots": {"main": {"contentmodel": "wikitext"}},
    }
    if content is not None:
        revision["slots"] = {"main": {"contentmodel": "wikitext", "content": content}}
    return {
        "pageid": page_id,
        "title": title,
        "fullurl": f"https://zh.wikisource.org/wiki/{title}",
        "revisions": [revision],
    }


def _query_payload(page: dict[str, object], **query: object) -> dict[str, object]:
    return {"query": {"pages": [page], **query}}


async def test_search_maps_zh_and_en_and_defaults_to_zh_without_content_n_plus_one(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(
            {
                "pageid": 100,
                "title": "論語",
                "fullurl": "https://zh.wikisource.org/wiki/%E8%AB%96%E8%AA%9E",
            }
        ),
    )
    httpx_mock.add_response(
        url=re.compile(r"https://en\.wikisource\.org/w/api\.php.*"),
        json=_query_payload({"pageid": 200, "title": "The Raven"}),
    )

    async with WikisourceClient() as client:
        zh = await client.search("論語", per_page=2, page=3)
        en = await client.search("raven", per_page=1, language="en")

    zh_request, en_request = httpx_mock.get_requests()
    assert zh_request.url.host == "zh.wikisource.org"
    assert zh_request.url.params["generator"] == "search"
    assert zh_request.url.params["gsrsearch"] == "論語"
    assert zh_request.url.params["gsrnamespace"] == "0"
    assert zh_request.url.params["gsrlimit"] == "2"
    assert zh_request.url.params["gsroffset"] == "4"
    assert zh_request.url.params["redirects"] == "1"
    assert "content" not in zh_request.url.params["rvprop"].split("|")
    assert en_request.url.host == "en.wikisource.org"

    zh_book = zh.results[0]
    assert zh.query == "論語"
    assert zh_book.source_record_id == "zh:100"
    assert zh_book.languages == ["zh"]
    assert zh_book.title == "論語"
    assert zh_book.source_url == "https://zh.wikisource.org/wiki/%E8%AB%96%E8%AA%9E"
    assert zh_book.access.status == "unknown"
    assert zh_book.resources[0].access.status == "unknown"
    assert en.results[0].source_record_id == "en:200"
    assert en.results[0].source_url == "https://en.wikisource.org/wiki/The_Raven"
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.parametrize("language", ["de", "https://evil.example", "zh.wikisource.org", "en@evil"])
async def test_language_allowlist_rejects_unknown_or_host_like_values_before_request(
    language: str,
    httpx_mock: HTTPXMock,
) -> None:
    async with WikisourceClient() as client:
        with pytest.raises(ValueError, match="Wikisource"):
            await client.search("book", language=language)

    assert httpx_mock.get_requests() == []


@pytest.mark.parametrize("per_page,page", [(0, 1), (21, 1), (1, 0)])
async def test_search_rejects_invalid_pagination_before_request(per_page: int, page: int) -> None:
    async with WikisourceClient() as client:
        with pytest.raises(ValueError):
            await client.search("book", per_page=per_page, page=page)


async def test_detail_follows_redirect_and_preserves_explicit_revision_slots_metadata(
    httpx_mock: HTTPXMock,
) -> None:
    header = _page(title="Canonical page", revision_id=789, size=30)
    content = "== Heading ==\n[[Target|Visible title]]\n{{template}}"
    content_page = _page(title="Canonical page", revision_id=789, size=30, content=content)
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(
            header, redirects=[{"from": "Redirected page", "to": "Canonical page"}]
        ),
    )
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(content_page),
    )

    async with WikisourceClient() as client:
        result = await client.get_page_detail(
            "Redirected page", revision_id=789, content_format="wikitext", max_content_chars=100
        )

    header_request, content_request = httpx_mock.get_requests()
    assert header_request.url.params["revids"] == "789"
    assert "titles" not in header_request.url.params
    assert header_request.url.params["redirects"] == "1"
    assert content_request.url.params["revids"] == "789"
    assert "content" in content_request.url.params["rvprop"]
    assert content_request.url.params["rvslots"] == "main"
    assert result.redirected_from == "Redirected page"
    assert result.page_id == 123
    assert result.canonical_title == "Canonical page"
    assert result.revision.revision_id == 789
    assert result.revision.parent_revision_id == 788
    assert result.revision.user == "Example editor"
    assert result.revision.comment == "fixture revision"
    assert result.revision.sha1 == "a" * 40
    assert result.revision.content_model == "wikitext"
    assert result.revision.content == content
    assert [(section.title, section.level) for section in result.sections] == [("Heading", 1)]


async def test_detail_missing_page_maps_to_not_found(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload({"title": "Missing", "missing": True}),
    )

    async with WikisourceClient() as client:
        with pytest.raises(NotFoundError, match="Missing"):
            await client.get_page_detail("Missing")

    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.parametrize(
    ("content_format", "expected_content", "expected_sections", "extra_response"),
    [
        ("wikitext", "== Heading ==\n[[Target|Visible]]", [("Heading", 1)], None),
        ("text", "Heading\nVisible", [("Heading", 1)], None),
        (
            "html",
            "<section><p>Rendered</p></section>",
            [],
            {"parse": {"text": "<section><p>Rendered</p></section>"}},
        ),
    ],
)
async def test_detail_content_format_is_labeled_and_bounded(
    content_format: str,
    expected_content: str,
    expected_sections: list[tuple[str, int]],
    extra_response: dict[str, object] | None,
    httpx_mock: HTTPXMock,
) -> None:
    raw_content = "== Heading ==\n[[Target|Visible]]"
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(_page(size=len(raw_content))),
    )
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(_page(size=len(raw_content), content=raw_content)),
    )
    if extra_response is not None:
        httpx_mock.add_response(
            url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"), json=extra_response
        )

    async with WikisourceClient() as client:
        result = await client.get_page_detail("Format page", content_format=content_format)  # type: ignore[arg-type]

    assert result.revision.content_format == content_format
    assert result.revision.content == expected_content
    assert [(section.title, section.level) for section in result.sections] == expected_sections
    requests = httpx_mock.get_requests()
    if content_format == "html":
        assert requests[-1].url.params["action"] == "parse"
        assert requests[-1].url.params["oldid"] == "456"
    else:
        assert len(requests) == 2


async def test_detail_does_not_fetch_declared_oversized_content(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(_page(size=100_001)),
    )

    async with WikisourceClient() as client:
        result = await client.get_page_detail("Large page", max_content_chars=100_000)

    assert result.revision.content == ""
    assert result.revision.content_truncated is True
    assert result.revision.next_start_offset == 0
    assert len(httpx_mock.get_requests()) == 1


async def test_detail_truncates_actual_body_and_direct_subpages_without_recursion(
    httpx_mock: HTTPXMock,
) -> None:
    raw_content = "abcdefghij"
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(_page(title="Parent", size=len(raw_content))),
    )
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(_page(title="Parent", size=len(raw_content), content=raw_content)),
    )
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json={
            "query": {
                "allpages": [
                    {"pageid": 1001, "title": "Parent/Child"},
                    {"pageid": 1002, "title": "Parent/Second child"},
                ]
            }
        },
    )

    async with WikisourceClient() as client:
        result = await client.get_page_detail(
            "Parent", max_content_chars=20, include_subpages=True, subpage_limit=2
        )

    assert result.revision.content == raw_content
    assert result.revision.content_truncated is False
    assert result.revision.next_start_offset is None
    assert [(item.page_id, item.title) for item in result.subpages] == [
        (1001, "Parent/Child"),
        (1002, "Parent/Second child"),
    ]
    requests = httpx_mock.get_requests()
    assert len(requests) == 3
    assert requests[-1].url.params["list"] == "allpages"
    assert requests[-1].url.params["apprefix"] == "Parent/"
    assert requests[-1].url.params["aplimit"] == "2"
    assert all(request.url.params.get("titles") != "Parent/Child" for request in requests)


async def test_detail_keeps_site_and_source_work_rights_separate_and_unknown(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(_page(size=2)),
    )
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"),
        json=_query_payload(_page(size=2, content="ok")),
    )

    async with WikisourceClient() as client:
        result = await client.get_page_detail("Rights page")

    assert result.site_content_access.status == "unknown"
    assert result.source_work_access.status == "unknown"
    assert result.site_content_access.notes != result.source_work_access.notes
    assert result.site_content_access.machine_download is None
    assert result.source_work_access.machine_download is None


async def test_search_maps_upstream_5xx(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=re.compile(r"https://zh\.wikisource\.org/w/api\.php.*"), status_code=503
    )

    async with WikisourceClient() as client:
        with pytest.raises(SourceUnavailableError):
            await client.search("book")


async def test_search_books_dispatches_explicit_wikisource_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(
        self: WikisourceClient, query: str, *, per_page: int, page: int = 1, language: str = "zh"
    ):
        assert (query, per_page, page, language) == ("book", 2, 1, "en")
        return type(
            "Response",
            (),
            {
                "query": query,
                "source": "wikisource",
                "total_results": None,
                "page": page,
                "per_page": per_page,
                "results": [],
            },
        )()

    monkeypatch.setattr(WikisourceClient, "search", fake_search)
    responses = await search_books("book", sources=["wikisource"], per_page=2, language="en")

    assert len(responses) == 1
    assert responses[0].source == "wikisource"


async def test_registry_detail_dispatch_and_public_facade_return_typed_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = WikisourcePage.model_validate(
        {
            "language": "zh",
            "site_url": "https://zh.wikisource.org",
            "page_id": 1,
            "title": "Page",
            "canonical_title": "Page",
            "source_url": "https://zh.wikisource.org/wiki/Page",
            "revision": {
                "revision_id": 2,
                "timestamp": "2024-01-01T00:00:00Z",
                "content": "body",
                "content_format": "wikitext",
            },
            "site_content_access": {"status": "unknown"},
            "source_work_access": {"status": "unknown"},
        }
    )

    async def fake_detail(self: WikisourceClient, title: str, **kwargs: object) -> WikisourcePage:
        assert title == "Page"
        assert kwargs == {
            "language": "en",
            "revision_id": 2,
            "content_format": "text",
            "max_content_chars": 10,
            "include_subpages": True,
            "subpage_limit": 1,
        }
        return expected

    monkeypatch.setattr(WikisourceClient, "get_page_detail", fake_detail)
    dispatched = await search_by_capability(
        "Page",
        "get_detail",
        sources=["wikisource"],
        title="Page",
        language="en",
        revision_id=2,
        content_format="text",
        max_content_chars=10,
        include_subpages=True,
        subpage_limit=1,
    )
    assert dispatched == [expected]

    async def fake_facade_dispatch(*args: object, **kwargs: object) -> list[WikisourcePage]:
        assert args == ("Facade page", "get_detail")
        assert kwargs["sources"] == ["wikisource"]
        assert kwargs["title"] == "Facade page"
        return [expected]

    monkeypatch.setattr("souwen.wikisource.search_by_capability", fake_facade_dispatch)
    assert await get_wikisource_page_detail("Facade page") is expected
