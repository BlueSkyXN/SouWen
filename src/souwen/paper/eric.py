"""ERIC official metadata search client.

Official API documentation: https://eric.ed.gov/?api
Authentication: none.  The API exposes metadata records through one anonymous
``GET /eric/`` endpoint using ``search``, ``start`` and ``rows`` parameters.
"""

from __future__ import annotations

from typing import Any

from souwen.core.exceptions import ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse

_BASE_URL = "https://api.ies.ed.gov"
_RECORD_URL = "https://eric.ed.gov/?id="
_FULLTEXT_URL = "https://files.eric.ed.gov/fulltext/"


class EricClient:
    """Search the official ERIC education-research metadata API without credentials."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="eric")

    async def __aenter__(self) -> EricClient:
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
    def _as_strings(value: object) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return []

    @staticmethod
    def _publication_year(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_record(record: dict[str, Any]) -> PaperResult:
        """Normalize one ERIC API document without inferring unavailable metadata."""
        record_id = record.get("id") if isinstance(record.get("id"), str) else ""
        title = record.get("title") if isinstance(record.get("title"), str) else ""
        authors = [Author(name=name) for name in EricClient._as_strings(record.get("author"))]
        description = record.get("description")
        abstract = (
            description.strip() if isinstance(description, str) and description.strip() else None
        )
        fulltext_authorized = record.get("e_fulltextauth") in {1, "1"}
        pdf_url = (
            f"{_FULLTEXT_URL}{record_id}.pdf"
            if fulltext_authorized and record_id.startswith("ED")
            else None
        )

        return PaperResult(
            source="eric",
            title=title,
            authors=authors,
            abstract=abstract,
            year=EricClient._publication_year(record.get("publicationdateyear")),
            journal=record.get("source") if isinstance(record.get("source"), str) else None,
            pdf_url=pdf_url,
            source_url=f"{_RECORD_URL}{record_id}" if record_id else "https://eric.ed.gov/",
            raw={
                "eric_id": record_id or None,
                "publication_types": EricClient._as_strings(record.get("publicationtype")),
                "subjects": EricClient._as_strings(record.get("subject")),
                "isbn": EricClient._as_strings(record.get("isbn")),
                "issn": EricClient._as_strings(record.get("issn")),
                "language": EricClient._as_strings(record.get("language")),
                "peer_reviewed": record.get("peerreviewed"),
                "publisher": record.get("publisher")
                if isinstance(record.get("publisher"), str)
                else None,
                "citation": record.get("sourceid")
                if isinstance(record.get("sourceid"), str)
                else None,
                "external_url": record.get("url") if isinstance(record.get("url"), str) else None,
                "fulltext_authorized": fulltext_authorized,
            },
        )

    async def search(
        self,
        query: str,
        rows: int = 10,
        start: int = 0,
    ) -> SearchResponse:
        """Search ERIC records using the documented offset pagination parameters."""
        if not 1 <= rows <= 2_000:
            raise ValueError("rows must be within 1..2000")
        if start < 0:
            raise ValueError("start must be greater than or equal to 0")

        response = await self._client.get(
            "/eric/",
            params={"search": query, "format": "json", "start": str(start), "rows": str(rows)},
        )
        payload = response.json()
        body = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(body, dict):
            raise ParseError("ERIC 响应缺少 response 对象")
        documents = body.get("docs")
        if not isinstance(documents, list):
            raise ParseError("ERIC 响应 docs 字段不是列表")

        results = [self._parse_record(item) for item in documents if isinstance(item, dict)]
        total = body.get("numFound")
        total_results = total if isinstance(total, int) else None
        return SearchResponse(
            query=query,
            source="eric",
            total_results=total_results,
            page=(start // rows) + 1,
            per_page=rows,
            results=results,
        )
