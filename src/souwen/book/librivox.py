"""Official LibriVox audiobook metadata client; never downloads audio."""

from __future__ import annotations

import mimetypes
from typing import Any, Literal

from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
    Author,
    BookAudioSection,
    BookIdentifier,
    BookResult,
    ResourceAccess,
    ResourceLink,
    SearchResponse,
)

_BASE_URL = "https://librivox.org"
_AUDIO_LIMIT = 50


class LibriVoxClient:
    """Read LibriVox catalog records and declared media links without fetching media."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="librivox")

    async def __aenter__(self) -> "LibriVoxClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    @staticmethod
    def _name(value: object) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else ""

    @classmethod
    def _authors(cls, value: object) -> list[Author]:
        if not isinstance(value, list):
            return []
        authors: list[Author] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = " ".join(
                part
                for part in (cls._name(item.get("first_name")), cls._name(item.get("last_name")))
                if part
            )
            if name:
                authors.append(Author(name=name))
        return authors

    @classmethod
    def _readers(cls, value: object) -> list[Author]:
        if not isinstance(value, list):
            return []
        readers: list[Author] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            name = cls._name(item.get("display_name"))
            if name and name not in seen:
                seen.add(name)
                readers.append(Author(name=name))
        return readers

    @staticmethod
    def _unique_readers(sections: list[BookAudioSection]) -> list[Author]:
        readers: list[Author] = []
        seen: set[str] = set()
        for section in sections:
            for reader in section.readers:
                if reader.name not in seen:
                    seen.add(reader.name)
                    readers.append(reader)
        return readers

    @staticmethod
    def _positive_int(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value >= 0 else None
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    @staticmethod
    def _http_url(value: object) -> str | None:
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
        return None

    @classmethod
    def _audio_sections(
        cls, value: object, access: ResourceAccess, *, audio_limit: int
    ) -> list[BookAudioSection]:
        if not isinstance(value, list):
            return []
        sections: list[BookAudioSection] = []
        for item in value:
            if not isinstance(item, dict) or len(sections) >= audio_limit:
                continue
            section_id = cls._name(item.get("id"))
            if not section_id:
                continue
            listen_url = cls._http_url(item.get("listen_url"))
            media_type, _ = mimetypes.guess_type(listen_url or "")
            file_name = cls._name(item.get("file_name")) or None
            title = cls._name(item.get("title")) or None
            number = cls._positive_int(item.get("section_number"))
            resource = None
            if listen_url is not None:
                resource = ResourceLink(
                    url=listen_url,
                    relation="audio",
                    label=(f"Section {number}: " if number is not None else "")
                    + (title or "Audio"),
                    file_name=file_name,
                    media_type=media_type,
                    format="MP3" if media_type == "audio/mpeg" else None,
                    source="librivox",
                    access=access.model_copy(deep=True),
                )
            sections.append(
                BookAudioSection(
                    source_section_id=section_id,
                    section_number=number,
                    title=title,
                    readers=cls._readers(item.get("readers")),
                    duration_seconds=cls._positive_int(item.get("playtime")),
                    resource=resource,
                )
            )
        return sections

    @classmethod
    def _parse(cls, item: dict[str, Any], *, audio_limit: int = _AUDIO_LIMIT) -> BookResult:
        ident, title = item.get("id"), item.get("title")
        if (
            not isinstance(ident, str)
            or not ident
            or not isinstance(title, str)
            or not title.strip()
        ):
            raise ParseError("LibriVox record 缺少 id 或 title")
        access = ResourceAccess(
            status="unknown",
            notes="LibriVox metadata/links do not establish public-domain status in every jurisdiction.",
        )
        sections = cls._audio_sections(item.get("sections"), access, audio_limit=audio_limit)
        readers = cls._unique_readers(sections)
        resources: list[ResourceLink] = []
        for key, relation, label, media_type, resource_format in (
            ("url_librivox", "catalog_record", "LibriVox page", None, None),
            ("url_rss", "rss", "LibriVox RSS", "application/rss+xml", "RSS"),
            ("url_iarchive", "external_catalog_record", "Internet Archive record", None, None),
            (
                "url_zip_file",
                "audio_archive",
                "LibriVox audio ZIP archive",
                "application/zip",
                "ZIP",
            ),
        ):
            url = cls._http_url(item.get(key))
            if url is not None:
                resources.append(
                    ResourceLink(
                        url=url,
                        relation=relation,
                        label=label,
                        media_type=media_type,
                        format=resource_format,
                        source="librivox",
                        access=access.model_copy(deep=True),
                    )
                )
        resources.extend(section.resource for section in sections if section.resource is not None)
        return BookResult(
            source="librivox",
            source_record_id=ident,
            title=title.strip(),
            authors=cls._authors(item.get("authors")),
            readers=readers,
            languages=[item["language"]] if isinstance(item.get("language"), str) else [],
            copyright_year=cls._positive_int(item.get("copyright_year")),
            description=item.get("description")
            if isinstance(item.get("description"), str)
            else None,
            identifiers=[BookIdentifier(scheme="source_record_id", value=ident)],
            audio_sections=sections,
            resources=resources,
            access=access,
            source_url=next(
                (x.url for x in resources if x.relation == "catalog_record"),
                f"{_BASE_URL}/audiobook/{ident}",
            ),
        )

    async def search(
        self,
        query: str,
        per_page: int = 10,
        page: int = 1,
        *,
        search_field: Literal["title", "author"] = "title",
    ) -> SearchResponse:
        if not 1 <= per_page <= 50 or page < 1:
            raise ValueError("per_page must be within 1..50 and page must be positive")
        if search_field not in {"title", "author"}:
            raise ValueError("search_field must be 'title' or 'author'")
        data = (
            await self._client.get(
                "/api/feed/audiobooks/",
                params={
                    search_field: query,
                    "format": "json",
                    "limit": per_page,
                    "offset": (page - 1) * per_page,
                },
            )
        ).json()
        books = data.get("books") if isinstance(data, dict) else None
        if not isinstance(books, list):
            raise ParseError("LibriVox 响应缺少 books")
        return SearchResponse(
            query=query,
            source="librivox",
            results=[self._parse(x) for x in books if isinstance(x, dict)],
            page=page,
            per_page=per_page,
        )

    async def get_by_id(self, audiobook_id: str, audio_limit: int = _AUDIO_LIMIT) -> BookResult:
        if not isinstance(audiobook_id, str) or not audiobook_id.isdigit():
            raise ValueError("audiobook_id 必须是数字 LibriVox ID")
        if not 1 <= audio_limit <= _AUDIO_LIMIT:
            raise ValueError(f"audio_limit must be within 1..{_AUDIO_LIMIT}")
        data = (
            await self._client.get(
                "/api/feed/audiobooks/",
                params={"id": audiobook_id, "format": "json", "extended": 1},
            )
        ).json()
        books = data.get("books") if isinstance(data, dict) else None
        if not isinstance(books, list) or not books:
            raise NotFoundError(f"LibriVox 未找到 audiobook: {audiobook_id}")
        record = next(
            (item for item in books if isinstance(item, dict) and item.get("id") == audiobook_id),
            None,
        )
        if record is None:
            raise NotFoundError(f"LibriVox 未找到 audiobook: {audiobook_id}")
        return self._parse(record, audio_limit=audio_limit)
