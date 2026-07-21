"""Official DOAB OAI-PMH client with bounded metadata-harvest search."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

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

_BASE_URL = "https://directory.doabooks.org"
_OAI_PATH = "/oai/request"
_BOOKS_SET = "com_20.500.12854_5"
_OAI_PREFIX = "oai:directory.doabooks.org:"
_MAX_PER_PAGE = 25


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


class DOABClient:
    """Read official DOAB OAI metadata; never requests a linked book file."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="doab")

    async def __aenter__(self) -> "DOABClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    @staticmethod
    def _values(element: ET.Element, name: str) -> list[str]:
        return [
            value
            for child in element.iter()
            if _local_name(child) == name
            if (value := _text(child))
        ]

    @staticmethod
    def _oai_identifier(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = value.strip()
        if normalized.startswith(_OAI_PREFIX):
            return normalized
        if normalized.startswith("20.500.12854/") and all(char not in normalized for char in "?#"):
            return f"{_OAI_PREFIX}{normalized}"
        return ""

    @classmethod
    def _record_id(cls, value: object) -> str:
        identifier = cls._oai_identifier(value)
        return identifier.removeprefix(_OAI_PREFIX) if identifier else ""

    @staticmethod
    def _url(value: object) -> str | None:
        if isinstance(value, str) and value.startswith(("https://", "http://")):
            return value.strip()
        return None

    @staticmethod
    def _size(value: object) -> int | None:
        try:
            size = int(str(value))
        except (TypeError, ValueError):
            return None
        return size if size >= 0 else None

    @classmethod
    def _parse_xml(cls, text: str) -> ET.Element:
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ParseError(f"DOAB OAI-PMH XML 解析失败: {exc}") from exc
        error = next((item for item in root.iter() if _local_name(item) == "error"), None)
        if error is not None:
            code = error.attrib.get("code")
            message = _text(error) or "unknown OAI-PMH error"
            if code == "idDoesNotExist":
                raise NotFoundError(f"DOAB 未找到 record: {message}")
            raise ParseError(f"DOAB OAI-PMH {code or 'error'}: {message}")
        return root

    @classmethod
    def _access(cls, dc: ET.Element) -> ResourceAccess:
        licenses = [
            child
            for child in dc.iter()
            if _local_name(child) == "licenseCondition" and _text(child)
        ]
        rights = cls._values(dc, "rights")
        license_text = _text(licenses[0]) if licenses else None
        license_url = licenses[0].attrib.get("uri") if licenses else None
        if license_url and not cls._url(license_url):
            license_url = None
        status = (
            "open_access" if any("open access" in value.lower() for value in rights) else "unknown"
        )
        return ResourceAccess(
            status=status,
            rights=license_text or (rights[0] if rights else None),
            license_url=license_url,
            notes=(
                "DOAB metadata dissemination is separate from each book's recorded license; "
                "linked files are not requested or downloaded."
            ),
        )

    @classmethod
    def _identifiers(cls, dc: ET.Element, oai_identifier: str) -> list[BookIdentifier]:
        identifiers = [BookIdentifier(scheme="source_record_id", value=oai_identifier)]
        for item in dc.iter():
            if _local_name(item) != "alternateIdentifier":
                continue
            value = _text(item)
            kind = item.attrib.get("type", "").lower()
            if kind == "isbn" and value:
                identifiers.append(
                    BookIdentifier(
                        scheme="isbn13" if len(value.replace("-", "")) == 13 else "isbn10",
                        value=value,
                    )
                )
            elif kind == "doi" and value:
                identifiers.append(
                    BookIdentifier(scheme="doi", value=value.removeprefix("https://doi.org/"))
                )
        return identifiers

    @classmethod
    def _resources(cls, dc: ET.Element, access: ResourceAccess) -> list[ResourceLink]:
        resources: list[ResourceLink] = []
        for item in dc.iter():
            if _local_name(item) != "identifier":
                continue
            url = cls._url(_text(item))
            if url is None:
                continue
            if "/handle/" in url and "directory.doabooks.org" in url:
                relation, label = "catalog_record", "DOAB record"
            elif "doi.org/" in url:
                relation, label = "doi", "DOI landing page"
            else:
                relation, label = "publisher_record", "Publisher record"
            resources.append(
                ResourceLink(
                    url=url,
                    relation=relation,
                    label=label,
                    source="doab",
                    access=access.model_copy(deep=True),
                )
            )
        return resources

    @classmethod
    def _parse_dc_record(cls, record: ET.Element) -> BookResult:
        header = next((item for item in record if _local_name(item) == "header"), None)
        metadata = next((item for item in record if _local_name(item) == "metadata"), None)
        if header is None or metadata is None:
            raise ParseError("DOAB OAI-PMH record 缺少 header 或 metadata")
        oai_identifier = (
            cls._values(header, "identifier")[0] if cls._values(header, "identifier") else ""
        )
        record_id = cls._record_id(oai_identifier)
        dc = next((item for item in metadata.iter() if _local_name(item) == "dc"), None)
        if not record_id or dc is None:
            raise ParseError("DOAB OAI-PMH record 缺少 identifier 或 oai_dc")
        titles = cls._values(dc, "title")
        if not titles:
            raise ParseError("DOAB OAI-PMH record 缺少 title")
        access = cls._access(dc)
        resources = cls._resources(dc, access)
        source_url = next(
            (resource.url for resource in resources if resource.relation == "catalog_record"),
            f"{_BASE_URL}/handle/{record_id}",
        )
        descriptions = [
            item for item in cls._values(dc, "description") if item.lower() != "published"
        ]
        return BookResult(
            source="doab",
            source_record_id=record_id,
            title=titles[0],
            authors=[Author(name=name) for name in cls._values(dc, "creator")],
            contributors=[Author(name=name) for name in cls._values(dc, "contributor")],
            languages=cls._values(dc, "language"),
            subjects=cls._values(dc, "subject"),
            publishers=cls._values(dc, "publisher"),
            description=descriptions[0] if descriptions else None,
            identifiers=cls._identifiers(dc, oai_identifier),
            resources=resources,
            access=access,
            source_url=source_url,
        )

    @classmethod
    def _with_bitstreams(
        cls, book: BookResult, mets_root: ET.Element, *, file_limit: int
    ) -> BookResult:
        resources = list(book.resources)
        for item in mets_root.iter():
            if _local_name(item) != "file" or len(resources) >= file_limit + len(book.resources):
                continue
            location = next((child for child in item if _local_name(child) == "FLocat"), None)
            if location is None:
                continue
            url = cls._url(location.attrib.get("{http://www.w3.org/1999/xlink}href"))
            if url is None:
                continue
            resources.append(
                ResourceLink(
                    url=url,
                    relation="bitstream",
                    label="DOAB bitstream metadata",
                    file_name=unquote(PurePosixPath(urlparse(url).path).name) or None,
                    size_bytes=cls._size(item.attrib.get("SIZE")),
                    media_type=item.attrib.get("MIMETYPE"),
                    source="doab",
                    access=book.access.model_copy(deep=True),
                )
            )
        return book.model_copy(update={"resources": resources})

    @classmethod
    def _matches_query(cls, book: BookResult, query: str) -> bool:
        needle = query.casefold()
        haystack = " ".join(
            [
                book.title,
                book.description or "",
                *(author.name for author in book.authors),
                *(author.name for author in book.contributors),
                *book.subjects,
                *book.publishers,
            ]
        ).casefold()
        return needle in haystack

    async def _oai(self, params: dict[str, str]) -> ET.Element:
        response = await self._client.get(_OAI_PATH, params=params)
        return self._parse_xml(response.text)

    async def search(self, query: str, per_page: int = 10, page: int = 1) -> SearchResponse:
        """Filter one bounded official Books-set harvest page; this is not global OAI search."""
        if not query.strip():
            raise ValueError("query 必须是非空字符串")
        if not 1 <= per_page <= _MAX_PER_PAGE or page != 1:
            raise ValueError(
                f"per_page must be within 1..{_MAX_PER_PAGE}; only page=1 is supported"
            )
        root = await self._oai(
            {"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": _BOOKS_SET}
        )
        records = [item for item in root.iter() if _local_name(item) == "record"]
        matches: list[BookResult] = []
        for record in records:
            try:
                book = self._parse_dc_record(record)
            except ParseError:
                continue
            if self._matches_query(book, query):
                matches.append(book)
            if len(matches) >= per_page:
                break
        return SearchResponse(
            query=query,
            source="doab",
            results=matches,
            page=1,
            per_page=per_page,
        )

    async def get_by_id(self, record_id: str, file_limit: int = 10) -> BookResult:
        identifier = self._oai_identifier(record_id)
        if not identifier or not 1 <= file_limit <= 25:
            raise ValueError("record_id 必须是 DOAB handle/OAI identifier，file_limit 必须在 1..25")
        dc_root = await self._oai(
            {"verb": "GetRecord", "metadataPrefix": "oai_dc", "identifier": identifier}
        )
        record = next((item for item in dc_root.iter() if _local_name(item) == "record"), None)
        if record is None:
            raise NotFoundError(f"DOAB 未找到 record: {record_id}")
        book = self._parse_dc_record(record)
        mets_root = await self._oai(
            {"verb": "GetRecord", "metadataPrefix": "mets", "identifier": identifier}
        )
        return self._with_bitstreams(book, mets_root, file_limit=file_limit)
