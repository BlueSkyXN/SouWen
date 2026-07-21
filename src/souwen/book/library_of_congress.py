"""Official Library of Congress JSON catalog client."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
    Author,
    BookIdentifier,
    BookResult,
    ResourceAccess,
    ResourceLink,
    SearchResponse,
)

_BASE_URL = "https://www.loc.gov"


class LibraryOfCongressClient:
    """Anonymous read-only LOC catalog client; it never downloads digital resources."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="library_of_congress")

    async def __aenter__(self) -> "LibraryOfCongressClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    @staticmethod
    def _strings(value: object, limit: int = 25) -> list[str]:
        values = value if isinstance(value, list) else [value]
        return [item.strip() for item in values if isinstance(item, str) and item.strip()][:limit]

    @staticmethod
    def _year(record: dict[str, Any]) -> int | None:
        for value in (
            record.get("date"),
            *LibraryOfCongressClient._strings(record.get("created_published")),
        ):
            if isinstance(value, str):
                match = re.search(r"(?<!\d)(\d{4})(?!\d)", value)
                if match:
                    return int(match.group(1))
        return None

    @staticmethod
    def _record_url(record: dict[str, Any]) -> str:
        value = record.get("id")
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            raise ParseError("LOC record 缺少官方 id URL")
        return value.replace("http://", "https://", 1)

    @classmethod
    def _access(cls, record: dict[str, Any]) -> ResourceAccess:
        rights = record.get("rights")
        rights_text = "; ".join(cls._strings(rights)) or None
        restricted = record.get("access_restricted") is True
        return ResourceAccess(
            status="restricted" if restricted else "metadata_only",
            rights=rights_text,
            notes="LOC record/resource access is item-specific; no download or reuse right is inferred.",
        )

    @classmethod
    def _identifiers(cls, record: dict[str, Any], record_id: str) -> list[BookIdentifier]:
        values = [BookIdentifier(scheme="source_record_id", value=record_id)]
        for scheme, field in (("lccn", "number_lccn"), ("isbn", "number_isbn")):
            for value in cls._strings(record.get(field)):
                compact = value.replace("-", "")
                if scheme == "isbn" and len(compact) in {10, 13}:
                    values.append(
                        BookIdentifier(
                            scheme="isbn10" if len(compact) == 10 else "isbn13", value=value
                        )
                    )
                elif scheme == "lccn":
                    values.append(BookIdentifier(scheme="lccn", value=value))
        return values

    @classmethod
    def _resources(cls, record: dict[str, Any], access: ResourceAccess) -> list[ResourceLink]:
        resources: list[ResourceLink] = []
        for item in (
            record.get("resources", []) if isinstance(record.get("resources"), list) else []
        ):
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or urlparse(url).scheme not in {"http", "https"}:
                continue
            resources.append(
                ResourceLink(
                    url=url,
                    relation="digital_resource",
                    label=item.get("caption") if isinstance(item.get("caption"), str) else None,
                    source="library_of_congress",
                    access=access.model_copy(deep=True),
                )
            )
        return resources[:20]

    @classmethod
    def _parse(cls, record: dict[str, Any]) -> BookResult:
        source_url = cls._record_url(record)
        title = record.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ParseError("LOC record 缺少 title")
        record_id = source_url.rstrip("/").rsplit("/", 1)[-1]
        access = cls._access(record)
        return BookResult(
            source="library_of_congress",
            source_record_id=record_id,
            title=title.strip(),
            authors=[Author(name=name) for name in cls._strings(record.get("contributors"))],
            languages=cls._strings(record.get("language")),
            subjects=cls._strings(record.get("subject")),
            collections=cls._strings(record.get("location")),
            first_publish_year=cls._year(record),
            identifiers=cls._identifiers(record, record_id),
            resources=cls._resources(record, access),
            access=access,
            source_url=source_url,
        )

    async def search(self, query: str, per_page: int = 10, page: int = 1) -> SearchResponse:
        if not 1 <= per_page <= 100 or page < 1:
            raise ValueError("per_page must be within 1..100 and page must be positive")
        response = await self._client.get(
            "/books/", params={"q": query, "fo": "json", "c": per_page, "sp": page}
        )
        payload = response.json()
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ParseError("LOC search 响应缺少 results")
        results = []
        for row in rows:
            if isinstance(row, dict):
                try:
                    results.append(self._parse(row))
                except ParseError:
                    continue
        pagination = payload.get("pagination") if isinstance(payload, dict) else {}
        total = pagination.get("total") if isinstance(pagination, dict) else None
        return SearchResponse(
            query=query,
            source="library_of_congress",
            total_results=total if isinstance(total, int) else None,
            results=results,
            page=page,
            per_page=per_page,
        )

    async def get_by_id(self, record_id: str) -> BookResult:
        if not isinstance(record_id, str) or not record_id.strip() or "/" in record_id.strip():
            raise ValueError("record_id 必须是 LOC item identifier")
        response = await self._client.get(f"/item/{record_id.strip()}/", params={"fo": "json"})
        payload = response.json()
        record = payload.get("item") if isinstance(payload, dict) else None
        if not isinstance(record, dict):
            raise NotFoundError(f"LOC 未找到 item: {record_id}")
        return self._parse(record)
