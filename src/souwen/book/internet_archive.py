"""Official Internet Archive Advanced Search and Metadata API client."""

from __future__ import annotations

import mimetypes
import re
from typing import Any
from urllib.parse import quote

from souwen.core.exceptions import ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
    Author,
    BookIdentifier,
    BookResult,
    ResourceAccess,
    ResourceLink,
    SearchResponse,
)

_BASE_URL = "https://archive.org"
_SEARCH_FIELDS = (
    "identifier",
    "title",
    "creator",
    "date",
    "year",
    "language",
    "subject",
    "collection",
    "description",
    "rights",
    "licenseurl",
    "access-restricted",
    "loans__status",
    "lending___",
    "mediatype",
    "publisher",
)


class InternetArchiveClient:
    """Read-only book-catalog client; never borrows, reads, or downloads files."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="internet_archive")

    async def __aenter__(self) -> "InternetArchiveClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    @staticmethod
    def _strings(value: object, *, limit: int = 25) -> list[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()][:limit]

    @staticmethod
    def _year(value: object) -> int | None:
        if isinstance(value, int) and 0 < value < 10000:
            return value
        if isinstance(value, str):
            match = re.search(r"(?<!\d)(\d{4})(?!\d)", value)
            return int(match.group(1)) if match else None
        return None

    @staticmethod
    def _truthy(value: object) -> bool:
        return value is True or (
            isinstance(value, str) and value.strip().lower() in {"1", "true", "yes"}
        )

    @staticmethod
    def _identifier(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = value.strip()
        if (
            not normalized
            or normalized in {".", ".."}
            or any(char in normalized for char in {"/", "\\"})
            or any(char.isspace() and char not in {" "} for char in normalized)
        ):
            return ""
        return normalized

    @staticmethod
    def _size_bytes(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value >= 0 else None
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    @classmethod
    def _access(cls, record: dict[str, Any]) -> ResourceAccess:
        rights = record.get("rights") if isinstance(record.get("rights"), str) else None
        license_url = (
            record.get("licenseurl") if isinstance(record.get("licenseurl"), str) else None
        )
        if cls._truthy(record.get("access-restricted")):
            status = "restricted"
        elif any(record.get(key) for key in ("loans__status", "lending___")):
            status = "borrow"
        elif license_url and "creativecommons.org/publicdomain" in license_url.lower():
            status = "public_domain"
        elif license_url and "creativecommons.org/licenses/" in license_url.lower():
            status = "open_access"
        else:
            status = "metadata_only"
        return ResourceAccess(status=status, rights=rights, license_url=license_url)

    @classmethod
    def _parse_record(
        cls, record: dict[str, Any], *, include_files: bool = False, file_limit: int = 20
    ) -> BookResult:
        identifier = cls._identifier(record.get("identifier"))
        title = record.get("title")
        if not identifier or not isinstance(title, str) or not title.strip():
            raise ParseError("Internet Archive record 缺少 identifier 或 title")
        access = cls._access(record)
        resources: list[ResourceLink] = []
        if include_files:
            files = record.get("files")
            if isinstance(files, list):
                for item in files:
                    if not isinstance(item, dict) or cls._truthy(item.get("private")):
                        continue
                    name = item.get("name")
                    if not isinstance(name, str) or not name.strip():
                        continue
                    name = name.strip()
                    size_bytes = cls._size_bytes(item.get("size"))
                    media_type, _ = mimetypes.guess_type(name)
                    resources.append(
                        ResourceLink(
                            url=f"{_BASE_URL}/download/{quote(identifier, safe='')}/{quote(name, safe='')}",
                            relation="file",
                            label=name,
                            file_name=name,
                            size_bytes=size_bytes,
                            media_type=media_type,
                            format=item.get("format")
                            if isinstance(item.get("format"), str)
                            else None,
                            source="internet_archive",
                            access=access.model_copy(deep=True),
                        )
                    )
                    if len(resources) >= file_limit:
                        break
        return BookResult(
            source="internet_archive",
            source_record_id=identifier,
            title=title.strip(),
            authors=[Author(name=name) for name in cls._strings(record.get("creator"))],
            languages=cls._strings(record.get("language")),
            subjects=cls._strings(record.get("subject")),
            collections=cls._strings(record.get("collection")),
            publishers=cls._strings(record.get("publisher")),
            first_publish_year=cls._year(record.get("year") or record.get("date")),
            description=record.get("description")
            if isinstance(record.get("description"), str)
            else None,
            identifiers=[BookIdentifier(scheme="source_record_id", value=identifier)],
            resources=resources,
            access=access,
            source_url=f"{_BASE_URL}/details/{quote(identifier, safe='')}",
        )

    async def search(self, query: str, per_page: int = 10, page: int = 1) -> SearchResponse:
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be within 1..100")
        if page < 1:
            raise ValueError("page must be greater than or equal to 1")
        response = await self._client.get(
            "/advancedsearch.php",
            params={
                "q": f"mediatype:texts AND ({query})",
                "fl[]": list(_SEARCH_FIELDS),
                "rows": per_page,
                "page": page,
                "output": "json",
            },
        )
        payload = response.json()
        body = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(body, dict) or not isinstance(body.get("docs"), list):
            raise ParseError("Internet Archive advanced search 响应缺少 docs")
        results: list[BookResult] = []
        for item in body["docs"]:
            if isinstance(item, dict):
                try:
                    results.append(self._parse_record(item))
                except ParseError:
                    continue
        total = body.get("numFound")
        return SearchResponse(
            query=query,
            source="internet_archive",
            total_results=total if isinstance(total, int) and total >= 0 else None,
            page=page,
            per_page=per_page,
            results=results,
        )

    async def get_by_identifier(self, identifier: str, file_limit: int = 20) -> BookResult:
        normalized = self._identifier(identifier)
        if not normalized or not 1 <= file_limit <= 50:
            raise ValueError("identifier 非法或 file_limit 必须在 1..50")
        response = await self._client.get(f"/metadata/{quote(normalized, safe='')}")
        payload = response.json()
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        if not isinstance(metadata, dict):
            raise ParseError("Internet Archive metadata 响应缺少 metadata")
        record = dict(metadata)
        record["files"] = payload.get("files") if isinstance(payload.get("files"), list) else []
        return self._parse_record(record, include_files=True, file_limit=file_limit)
