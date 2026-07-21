"""Bounded, language-allowlisted Wikisource MediaWiki Action API client.

This module only reads page metadata and explicitly requested revisions.  It
does not import Wikimedia dumps, crawl related pages, or infer that a hosted
text is public domain in every jurisdiction.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from typing import Any, Literal
from urllib.parse import quote

from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
    BookIdentifier,
    BookResult,
    ResourceAccess,
    ResourceLink,
    SearchResponse,
    WikisourcePage,
    WikisourcePageReference,
    WikisourceRevision,
    WikisourceSection,
)

DEFAULT_WIKISOURCE_LANGUAGE = "zh"
WIKISOURCE_SITES: dict[str, str] = {
    "zh": "https://zh.wikisource.org",
    "en": "https://en.wikisource.org",
}
_CONTENT_FORMATS = frozenset({"wikitext", "text", "html"})
_SECTION_RE = re.compile(r"^(={2,6})\s*(.*?)\s*\1\s*$", flags=re.MULTILINE)
_COMMENT_RE = re.compile(r"<!--.*?-->", flags=re.DOTALL)
_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
_LINK_RE = re.compile(r"\[\[([^\]|]+)\|?([^\]]*)\]\]")


class WikisourceClient:
    """Read a fixed allowlist of Wikisource sites through the Action API."""

    def __init__(self) -> None:
        # Deliberately omit source_name: a user-supplied language must never
        # select a configurable arbitrary base URL.
        self._client = SouWenHttpClient()

    async def __aenter__(self) -> "WikisourceClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    @staticmethod
    def _language(value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("language 必须是受支持的 Wikisource 语言代码")
        language = value.strip().lower()
        if language not in WIKISOURCE_SITES:
            supported = ", ".join(sorted(WIKISOURCE_SITES))
            raise ValueError(f"language 必须是受支持的 Wikisource 语言代码: {supported}")
        return language

    @staticmethod
    def _title(value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("title 必须是非空字符串")
        title = value.strip()
        if not title or len(title) > 512 or any(char in title for char in "\r\n\x00"):
            raise ValueError("title 必须是长度不超过 512 的非空页面标题")
        return title

    @classmethod
    def _site_url(cls, language: object) -> tuple[str, str]:
        normalized = cls._language(language)
        return normalized, WIKISOURCE_SITES[normalized]

    @staticmethod
    def _page_url(site_url: str, title: str) -> str:
        return f"{site_url}/wiki/{quote(title.replace(' ', '_'), safe='/:()')}"

    @staticmethod
    def _pages(payload: object, *, allow_empty: bool = False) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ParseError("Wikisource Action API 响应不是对象")
        query = payload.get("query")
        pages = query.get("pages") if isinstance(query, dict) else None
        if not isinstance(pages, list):
            if allow_empty and isinstance(query, dict):
                return []
            if allow_empty and payload.get("batchcomplete") == "":
                return []
            raise ParseError("Wikisource Action API 响应缺少 query.pages")
        return [page for page in pages if isinstance(page, dict)]

    @staticmethod
    def _page_id(page: Mapping[str, Any]) -> int:
        page_id = page.get("pageid")
        if not isinstance(page_id, int) or page_id <= 0:
            raise ParseError("Wikisource 页面缺少有效 pageid")
        return page_id

    @staticmethod
    def _page_title(page: Mapping[str, Any]) -> str:
        title = page.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ParseError("Wikisource 页面缺少标题")
        return title.strip()

    @classmethod
    def _revision_header(cls, page: Mapping[str, Any]) -> dict[str, Any]:
        revisions = page.get("revisions")
        if not isinstance(revisions, list) or not revisions or not isinstance(revisions[0], dict):
            raise ParseError("Wikisource 页面缺少 revision")
        revision = revisions[0]
        revision_id = revision.get("revid")
        timestamp = revision.get("timestamp")
        if not isinstance(revision_id, int) or revision_id <= 0 or not isinstance(timestamp, str):
            raise ParseError("Wikisource revision 缺少 id 或 timestamp")
        return revision

    @staticmethod
    def _site_content_access() -> ResourceAccess:
        return ResourceAccess(
            status="unknown",
            notes=(
                "Wikisource page/revision metadata only. The site contribution license and "
                "the underlying source-work copyright require separate page- and jurisdiction-specific evidence."
            ),
        )

    @staticmethod
    def _source_work_access() -> ResourceAccess:
        return ResourceAccess(
            status="unknown",
            notes="Wikisource hosting does not establish public-domain or redistribution rights.",
        )

    @staticmethod
    def _sections(content: str) -> list[WikisourceSection]:
        sections: list[WikisourceSection] = []
        for match in _SECTION_RE.finditer(content):
            title = match.group(2).strip()
            if title:
                sections.append(
                    WikisourceSection(
                        title=title, level=len(match.group(1)) - 1, start_offset=match.start()
                    )
                )
        return sections

    @staticmethod
    def _plain_text(wikitext: str) -> str:
        """Return a deliberately simple local text projection, never rendered HTML."""

        text = _COMMENT_RE.sub("", wikitext)
        previous = None
        while text != previous:
            previous = text
            text = _TEMPLATE_RE.sub("", text)

        def replace_link(match: re.Match[str]) -> str:
            label = match.group(2).strip()
            return label or match.group(1).strip()

        text = _LINK_RE.sub(replace_link, text)
        text = re.sub(r"'{2,5}", "", text)
        text = re.sub(r"^={2,6}\s*(.*?)\s*={2,6}$", r"\1", text, flags=re.MULTILINE)
        return html.unescape(text).strip()

    @staticmethod
    def _truncate(content: str, maximum: int) -> tuple[str, bool, int | None]:
        if len(content) <= maximum:
            return content, False, None
        return content[:maximum], True, maximum

    async def _query(self, site_url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.get(
            f"{site_url}/w/api.php",
            params={"action": "query", "format": "json", "formatversion": 2, **params},
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ParseError("Wikisource Action API 响应不是对象")
        if isinstance(payload.get("error"), dict):
            raise ParseError("Wikisource Action API 返回 error")
        return payload

    async def search(
        self,
        query: str,
        per_page: int = 10,
        page: int = 1,
        language: str = DEFAULT_WIKISOURCE_LANGUAGE,
    ) -> SearchResponse:
        """Search namespace-0 Wikisource pages without fetching revision content."""

        if not isinstance(query, str) or not query.strip():
            raise ValueError("query 必须是非空字符串")
        if not 1 <= per_page <= 20:
            raise ValueError("per_page must be within 1..20")
        if page < 1:
            raise ValueError("page must be greater than or equal to 1")
        normalized_language, site_url = self._site_url(language)
        payload = await self._query(
            site_url,
            {
                "generator": "search",
                "gsrsearch": query.strip(),
                "gsrnamespace": 0,
                "gsrlimit": per_page,
                "gsroffset": (page - 1) * per_page,
                "prop": "info|revisions",
                "inprop": "url",
                "rvlimit": 1,
                "rvprop": "ids|timestamp|size|contentmodel",
                "rvslots": "main",
                "redirects": 1,
            },
        )
        pages = self._pages(payload, allow_empty=True)
        results: list[BookResult] = []
        for item in sorted(pages, key=lambda value: value.get("index", 0)):
            if item.get("missing") is True:
                continue
            try:
                page_id = self._page_id(item)
                title = self._page_title(item)
                source_url = item.get("fullurl")
                if not isinstance(source_url, str) or not source_url.startswith(
                    f"{site_url}/wiki/"
                ):
                    source_url = self._page_url(site_url, title)
                results.append(
                    BookResult(
                        source="wikisource",
                        source_record_id=f"{normalized_language}:{page_id}",
                        title=title,
                        languages=[normalized_language],
                        identifiers=[
                            BookIdentifier(
                                scheme="source_record_id", value=f"{normalized_language}:{page_id}"
                            )
                        ],
                        resources=[
                            ResourceLink(
                                url=source_url,
                                relation="external_catalog_record",
                                label="Wikisource page",
                                source="wikisource",
                                access=self._source_work_access(),
                            )
                        ],
                        access=self._source_work_access(),
                        source_url=source_url,
                    )
                )
            except ParseError:
                continue
        return SearchResponse(
            query=query.strip(),
            source="wikisource",
            total_results=None,
            page=page,
            per_page=per_page,
            results=results,
        )

    async def _page_header(
        self,
        *,
        site_url: str,
        title: str,
        revision_id: int | None,
    ) -> tuple[dict[str, Any], dict[str, Any], str | None]:
        selector: dict[str, Any] = (
            {"revids": revision_id} if revision_id is not None else {"titles": title}
        )
        payload = await self._query(
            site_url,
            {
                **selector,
                "redirects": 1,
                "prop": "info|revisions",
                "inprop": "url",
                "rvlimit": 1,
                "rvprop": "ids|timestamp|size|contentmodel|user|comment|sha1",
                "rvslots": "main",
            },
        )
        pages = self._pages(payload)
        if not pages or pages[0].get("missing") is True:
            raise NotFoundError(f"Wikisource 未找到页面: {title}")
        page = pages[0]
        revision = self._revision_header(page)
        redirects = (
            payload.get("query", {}).get("redirects")
            if isinstance(payload.get("query"), dict)
            else None
        )
        redirected_from = None
        if isinstance(redirects, list):
            for item in redirects:
                if isinstance(item, dict) and isinstance(item.get("from"), str):
                    redirected_from = item["from"]
                    break
        return page, revision, redirected_from

    async def _revision_content(
        self,
        *,
        site_url: str,
        revision_id: int,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = await self._query(
            site_url,
            {
                "revids": revision_id,
                "prop": "info|revisions",
                "inprop": "url",
                "rvlimit": 1,
                "rvprop": "ids|timestamp|size|contentmodel|content|user|comment|sha1",
                "rvslots": "main",
            },
        )
        pages = self._pages(payload)
        if not pages or pages[0].get("missing") is True:
            raise NotFoundError(f"Wikisource 未找到 revision: {revision_id}")
        page = pages[0]
        return page, self._revision_header(page)

    async def _subpages(
        self,
        *,
        site_url: str,
        title: str,
        limit: int,
    ) -> list[WikisourcePageReference]:
        if limit == 0:
            return []
        payload = await self._query(
            site_url,
            {"list": "allpages", "apprefix": f"{title}/", "apnamespace": 0, "aplimit": limit},
        )
        query = payload.get("query")
        pages = query.get("allpages") if isinstance(query, dict) else None
        if not isinstance(pages, list):
            raise ParseError("Wikisource 子页面响应缺少 query.allpages")
        references: list[WikisourcePageReference] = []
        for item in pages:
            if not isinstance(item, dict):
                continue
            try:
                page_id = self._page_id(item)
                child_title = self._page_title(item)
            except ParseError:
                continue
            references.append(
                WikisourcePageReference(
                    page_id=page_id,
                    title=child_title,
                    source_url=self._page_url(site_url, child_title),
                )
            )
        return references

    async def get_page_detail(
        self,
        title: str,
        *,
        language: str = DEFAULT_WIKISOURCE_LANGUAGE,
        revision_id: int | None = None,
        content_format: Literal["wikitext", "text", "html"] = "wikitext",
        max_content_chars: int = 100_000,
        include_subpages: bool = False,
        subpage_limit: int = 10,
    ) -> WikisourcePage:
        """Read one explicit revision with bounded content and optional direct subpages."""

        requested_title = self._title(title)
        normalized_language, site_url = self._site_url(language)
        if revision_id is not None and (
            isinstance(revision_id, bool) or not isinstance(revision_id, int) or revision_id <= 0
        ):
            raise ValueError("revision_id 必须是正整数或 None")
        if content_format not in _CONTENT_FORMATS:
            raise ValueError("content_format 必须为 wikitext、text 或 html")
        if not 1 <= max_content_chars <= 200_000:
            raise ValueError("max_content_chars must be within 1..200000")
        if not 0 <= subpage_limit <= 50:
            raise ValueError("subpage_limit must be within 0..50")

        page, header, redirected_from = await self._page_header(
            site_url=site_url, title=requested_title, revision_id=revision_id
        )
        page_id = self._page_id(page)
        canonical_title = self._page_title(page)
        canonical_url = page.get("fullurl")
        if not isinstance(canonical_url, str) or not canonical_url.startswith(f"{site_url}/wiki/"):
            canonical_url = self._page_url(site_url, canonical_title)
        declared_size = header.get("size")
        size_bytes = (
            declared_size if isinstance(declared_size, int) and declared_size >= 0 else None
        )
        actual_revision_id = header["revid"]
        content = ""
        section_source = ""
        truncated = False
        omitted_due_to_size = False
        next_start_offset: int | None = None
        content_model = None
        slot = header.get("slots")
        if isinstance(slot, dict) and isinstance(slot.get("main"), dict):
            content_model = slot["main"].get("contentmodel")

        if size_bytes is None or size_bytes <= max_content_chars:
            content_page, content_revision = await self._revision_content(
                site_url=site_url, revision_id=actual_revision_id
            )
            content = self._content_from_revision(content_revision)
            section_source = content
            slot = content_revision.get("slots")
            if isinstance(slot, dict) and isinstance(slot.get("main"), dict):
                raw_content_model = slot["main"].get("contentmodel")
                content_model = (
                    raw_content_model if isinstance(raw_content_model, str) else content_model
                )
            if content_format == "text":
                content = self._plain_text(content)
            elif content_format == "html":
                content = await self._render_html(site_url, actual_revision_id)
            content, truncated, next_start_offset = self._truncate(content, max_content_chars)
            page_id = self._page_id(content_page)
            canonical_title = self._page_title(content_page)
        else:
            # The upstream revision itself declares a larger body.  Return its
            # provenance but no body, rather than fetching a massive response.
            truncated = True
            omitted_due_to_size = True
            next_start_offset = 0

        subpages = (
            await self._subpages(site_url=site_url, title=canonical_title, limit=subpage_limit)
            if include_subpages
            else []
        )
        return WikisourcePage(
            language=normalized_language,
            site_url=site_url,
            page_id=page_id,
            title=canonical_title,
            canonical_title=canonical_title,
            source_url=canonical_url,
            revision=WikisourceRevision(
                revision_id=actual_revision_id,
                parent_revision_id=header.get("parentid")
                if isinstance(header.get("parentid"), int)
                else None,
                timestamp=header["timestamp"],
                user=header.get("user") if isinstance(header.get("user"), str) else None,
                comment=header.get("comment") if isinstance(header.get("comment"), str) else None,
                content_model=content_model if isinstance(content_model, str) else None,
                sha1=header.get("sha1") if isinstance(header.get("sha1"), str) else None,
                content=content,
                content_format=content_format,
                content_size_bytes=size_bytes,
                content_truncated=truncated,
                content_omitted_due_to_size=omitted_due_to_size,
                next_start_offset=next_start_offset,
            ),
            redirected_from=redirected_from,
            sections=self._sections(section_source) if content_format != "html" else [],
            parent_title=canonical_title.rsplit("/", 1)[0] if "/" in canonical_title else None,
            subpages=subpages,
            site_content_access=self._site_content_access(),
            source_work_access=self._source_work_access(),
        )

    @staticmethod
    def _content_from_revision(revision: Mapping[str, Any]) -> str:
        slots = revision.get("slots")
        main = slots.get("main") if isinstance(slots, dict) else None
        content = main.get("content") if isinstance(main, dict) else None
        if not isinstance(content, str):
            raise ParseError("Wikisource revision 缺少 slots.main.content")
        return content

    async def _render_html(self, site_url: str, revision_id: int) -> str:
        response = await self._client.get(
            f"{site_url}/w/api.php",
            params={
                "action": "parse",
                "format": "json",
                "formatversion": 2,
                "oldid": revision_id,
                "prop": "text",
                "disableeditsection": 1,
                "disablelimitreport": 1,
            },
        )
        payload = response.json()
        parsed = payload.get("parse") if isinstance(payload, dict) else None
        text = parsed.get("text") if isinstance(parsed, dict) else None
        if not isinstance(text, str):
            raise ParseError("Wikisource parse 响应缺少 HTML text")
        return text


__all__ = ["DEFAULT_WIKISOURCE_LANGUAGE", "WIKISOURCE_SITES", "WikisourceClient"]
