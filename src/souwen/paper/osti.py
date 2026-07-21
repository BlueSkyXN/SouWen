"""OSTI.GOV official anonymous metadata search and record-detail client.

The public OSTI API exposes records through ``/api/v1/records``.  Keyword
searches use the documented ``q`` parameter; individual records use their
OSTI identifier in the path.  A ``fulltext`` link is retained as provenance,
not treated as a license or redistribution assertion.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse

_BASE_URL = "https://www.osti.gov"
_RECORD_URL = "https://www.osti.gov/biblio/"
_YEAR_RE = re.compile(r"^(\d{4})")
_OSTI_ID_RE = re.compile(r"^\d+$")


class OstiClient:
    """Query OSTI.GOV's official, credential-free records API."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="osti")

    async def __aenter__(self) -> OstiClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def _as_text(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    @staticmethod
    def _as_strings(value: object) -> list[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @classmethod
    def _authors(cls, value: object) -> list[Author]:
        """Normalize the documented string records and tolerate name mappings."""
        if not isinstance(value, list):
            return [Author(name=name) for name in cls._as_strings(value)]

        authors: list[Author] = []
        for item in value:
            if isinstance(item, str):
                name = cls._as_text(item)
            elif isinstance(item, Mapping):
                name = cls._as_text(item.get("name"))
                if name is None:
                    parts = [
                        cls._as_text(item.get(field))
                        for field in ("first_name", "middle_name", "last_name")
                    ]
                    name = " ".join(part for part in parts if part) or None
            else:
                name = None
            if name:
                authors.append(Author(name=name))
        return authors

    @classmethod
    def _parse_record(cls, record: Mapping[str, Any]) -> PaperResult:
        """Normalize one OSTI record without inferring rights from resource links."""
        osti_id = cls._as_text(record.get("osti_id"))
        publication_date = cls._as_text(record.get("publication_date"))
        year_match = _YEAR_RE.match(publication_date or "")

        links = record.get("links")
        resource_links = (
            [item for item in links if isinstance(item, Mapping)] if isinstance(links, list) else []
        )

        return PaperResult(
            source="osti",
            title=cls._as_text(record.get("title")) or "",
            authors=cls._authors(record.get("authors")),
            abstract=cls._as_text(record.get("description")),
            doi=cls._as_text(record.get("doi")),
            year=int(year_match.group(1)) if year_match else None,
            publication_date=publication_date,
            source_url=f"{_RECORD_URL}{osti_id}" if osti_id else "https://www.osti.gov/",
            raw={
                "osti_id": osti_id,
                "product_type": cls._as_text(record.get("product_type")),
                "subjects": cls._as_strings(record.get("subjects")),
                "sponsor_orgs": cls._as_strings(record.get("sponsor_orgs")),
                "research_orgs": cls._as_strings(record.get("research_orgs")),
                # Keep the official relation/href data.  Its presence alone says nothing
                # about license, open-access status, or redistribution permission.
                "resource_links": [dict(item) for item in resource_links],
            },
        )

    @staticmethod
    def _records(payload: object, *, context: str) -> list[Mapping[str, Any]]:
        if not isinstance(payload, list):
            raise ParseError(f"OSTI {context} 响应不是 records 数组")
        if not all(isinstance(item, Mapping) for item in payload):
            raise ParseError(f"OSTI {context} records 包含非对象项")
        return payload

    async def search(self, query: str, rows: int = 10, page: int = 1) -> SearchResponse:
        """Search official OSTI records using ``q``, ``rows`` and ``page``."""
        query = query.strip() if isinstance(query, str) else ""
        if not query:
            raise ValueError("query must be a non-empty string")
        if rows < 1:
            raise ValueError("rows must be greater than or equal to 1")
        if page < 1:
            raise ValueError("page must be greater than or equal to 1")

        response = await self._client.get(
            "/api/v1/records",
            params={"q": query, "rows": str(rows), "page": str(page)},
        )
        records = self._records(response.json(), context="search")
        total_value = response.headers.get("x-total-count")
        try:
            total_results = int(total_value) if total_value is not None else len(records)
        except ValueError:
            total_results = len(records)

        return SearchResponse(
            query=query,
            source="osti",
            total_results=total_results,
            page=page,
            per_page=rows,
            results=[self._parse_record(record) for record in records],
        )

    async def get_by_id(self, osti_id: str) -> PaperResult:
        """Fetch and normalize one OSTI record by its official identifier."""
        normalized_id = osti_id.strip() if isinstance(osti_id, str) else ""
        if not _OSTI_ID_RE.fullmatch(normalized_id):
            raise ValueError("osti_id must be a non-empty numeric OSTI record ID")

        response = await self._client.get(f"/api/v1/records/{normalized_id}")
        if response.status_code == 404:
            raise NotFoundError(f"OSTI 未找到 ID: {normalized_id}")
        records = self._records(response.json(), context="detail")
        if not records:
            raise NotFoundError(f"OSTI 未找到 ID: {normalized_id}")
        return self._parse_record(records[0])
