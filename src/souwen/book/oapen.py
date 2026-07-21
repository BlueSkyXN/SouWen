"""Official OAPEN OAI-PMH client with bounded metadata-harvest search."""

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

_BASE_URL = "https://library.oapen.org"
_OAI_PATH = "/oai/request"
_BOOKS_SET = "com_20.500.12657_5"
_OAI_PREFIX = "oai:library.oapen.org:"
_MAX_PER_PAGE = 25


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


class OAPENClient:
    """Read OAPEN OAI metadata and declared file links; never downloads a file."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="oapen")

    async def __aenter__(self) -> "OAPENClient":
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
    def _url(value: object) -> str | None:
        return (
            value.strip()
            if isinstance(value, str) and value.startswith(("https://", "http://"))
            else None
        )

    @staticmethod
    def _oai_identifier(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = value.strip()
        if normalized.startswith(_OAI_PREFIX):
            return normalized
        if normalized.startswith("20.500.12657/") and not any(char in normalized for char in "?#"):
            return f"{_OAI_PREFIX}{normalized}"
        return ""

    @classmethod
    def _parse_xml(cls, text: str) -> ET.Element:
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ParseError(f"OAPEN OAI-PMH XML 解析失败: {exc}") from exc
        error = next((item for item in root.iter() if _local_name(item) == "error"), None)
        if error is not None:
            if error.attrib.get("code") == "idDoesNotExist":
                raise NotFoundError(f"OAPEN 未找到 record: {_text(error)}")
            raise ParseError(f"OAPEN OAI-PMH {error.attrib.get('code', 'error')}: {_text(error)}")
        return root

    @classmethod
    def _access(cls, dc: ET.Element) -> ResourceAccess:
        license_node = next(
            (item for item in dc.iter() if _local_name(item) == "licenseCondition" and _text(item)),
            None,
        )
        rights = cls._values(dc, "rights")
        license_url = license_node.attrib.get("uri") if license_node is not None else None
        if license_url and cls._url(license_url) is None:
            license_url = None
        return ResourceAccess(
            status="open_access"
            if any("openaccess" in item.lower().replace("-", "") for item in rights)
            else "unknown",
            rights=_text(license_node) or (rights[0] if rights else None),
            license_url=license_url,
            notes="OAPEN metadata and each book's recorded license are separate; linked files are not downloaded.",
        )

    @classmethod
    def _resources(cls, dc: ET.Element, access: ResourceAccess) -> list[ResourceLink]:
        resources: list[ResourceLink] = []
        for node in dc.iter():
            if _local_name(node) != "identifier":
                continue
            url = cls._url(_text(node))
            if url is None:
                continue
            if "/handle/" in url and "library.oapen.org" in url:
                relation, label = "catalog_record", "OAPEN record"
            elif "doi.org/" in url:
                relation, label = "doi", "DOI landing page"
            else:
                relation, label = "publisher_record", "Publisher record"
            resources.append(
                ResourceLink(
                    url=url,
                    relation=relation,
                    label=label,
                    source="oapen",
                    access=access.model_copy(deep=True),
                )
            )
        return resources

    @classmethod
    def _parse_dc_record(cls, record: ET.Element) -> BookResult:
        header = next((item for item in record if _local_name(item) == "header"), None)
        metadata = next((item for item in record if _local_name(item) == "metadata"), None)
        if header is None or metadata is None:
            raise ParseError("OAPEN OAI-PMH record 缺少 header 或 metadata")
        identifiers = cls._values(header, "identifier")
        oai_identifier = cls._oai_identifier(identifiers[0] if identifiers else None)
        record_id = oai_identifier.removeprefix(_OAI_PREFIX)
        dc = next((item for item in metadata.iter() if _local_name(item) == "dc"), None)
        if not record_id or dc is None:
            raise ParseError("OAPEN OAI-PMH record 缺少 identifier 或 oai_dc")
        titles = cls._values(dc, "title")
        if not titles:
            raise ParseError("OAPEN OAI-PMH record 缺少 title")
        access = cls._access(dc)
        resources = cls._resources(dc, access)
        normalized_identifiers = [BookIdentifier(scheme="source_record_id", value=oai_identifier)]
        for node in dc.iter():
            if _local_name(node) != "alternateIdentifier":
                continue
            value, kind = _text(node), node.attrib.get("type", "").lower()
            if kind == "doi" and value:
                normalized_identifiers.append(
                    BookIdentifier(scheme="doi", value=value.removeprefix("https://doi.org/"))
                )
            elif kind == "isbn" and value:
                normalized_identifiers.append(
                    BookIdentifier(
                        scheme="isbn13" if len(value.replace("-", "")) == 13 else "isbn10",
                        value=value,
                    )
                )
        descriptions = [
            item for item in cls._values(dc, "description") if item.lower() != "published"
        ]
        funding = cls._values(dc, "funderName")
        source_url = next(
            (item.url for item in resources if item.relation == "catalog_record"),
            f"{_BASE_URL}/handle/{record_id}",
        )
        return BookResult(
            source="oapen",
            source_record_id=record_id,
            title=titles[0],
            authors=[Author(name=item) for item in cls._values(dc, "creator")],
            contributors=[Author(name=item) for item in cls._values(dc, "contributor")],
            languages=cls._values(dc, "language"),
            subjects=cls._values(dc, "subject"),
            publishers=cls._values(dc, "publisher"),
            funding=funding,
            description=descriptions[0] if descriptions else None,
            identifiers=normalized_identifiers,
            resources=resources,
            access=access,
            source_url=source_url,
        )

    @staticmethod
    def _size(value: object) -> int | None:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @classmethod
    def _with_bitstreams(cls, book: BookResult, mets: ET.Element, *, file_limit: int) -> BookResult:
        resources = list(book.resources)
        initial_count = len(resources)
        for node in mets.iter():
            if _local_name(node) != "file" or len(resources) >= initial_count + file_limit:
                continue
            location = next((item for item in node if _local_name(item) == "FLocat"), None)
            url = (
                cls._url(location.attrib.get("{http://www.w3.org/1999/xlink}href"))
                if location is not None
                else None
            )
            if url is None:
                continue
            resources.append(
                ResourceLink(
                    url=url,
                    relation="bitstream",
                    label="OAPEN bitstream metadata",
                    file_name=unquote(PurePosixPath(urlparse(url).path).name) or None,
                    size_bytes=cls._size(node.attrib.get("SIZE")),
                    media_type=node.attrib.get("MIMETYPE"),
                    source="oapen",
                    access=book.access.model_copy(deep=True),
                )
            )
        return book.model_copy(update={"resources": resources})

    @classmethod
    def _matches(cls, book: BookResult, query: str) -> bool:
        corpus = " ".join(
            [
                book.title,
                book.description or "",
                *(item.name for item in book.authors),
                *(item.name for item in book.contributors),
                *book.subjects,
                *book.publishers,
                *book.funding,
            ]
        )
        return query.casefold() in corpus.casefold()

    async def _oai(self, params: dict[str, str]) -> ET.Element:
        return self._parse_xml((await self._client.get(_OAI_PATH, params=params)).text)

    async def search(self, query: str, per_page: int = 10, page: int = 1) -> SearchResponse:
        if not query.strip() or not 1 <= per_page <= _MAX_PER_PAGE or page != 1:
            raise ValueError(f"query 必须非空，per_page 必须在 1..{_MAX_PER_PAGE}，且仅支持 page=1")
        root = await self._oai(
            {"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": _BOOKS_SET}
        )
        results: list[BookResult] = []
        for record in (item for item in root.iter() if _local_name(item) == "record"):
            try:
                book = self._parse_dc_record(record)
            except ParseError:
                continue
            if self._matches(book, query):
                results.append(book)
            if len(results) >= per_page:
                break
        return SearchResponse(
            query=query, source="oapen", results=results, page=1, per_page=per_page
        )

    async def get_by_id(self, record_id: str, file_limit: int = 10) -> BookResult:
        identifier = self._oai_identifier(record_id)
        if not identifier or not 1 <= file_limit <= 25:
            raise ValueError(
                "record_id 必须是 OAPEN handle/OAI identifier，file_limit 必须在 1..25"
            )
        dc_root = await self._oai(
            {"verb": "GetRecord", "metadataPrefix": "oai_dc", "identifier": identifier}
        )
        record = next((item for item in dc_root.iter() if _local_name(item) == "record"), None)
        if record is None:
            raise NotFoundError(f"OAPEN 未找到 record: {record_id}")
        book = self._parse_dc_record(record)
        mets = await self._oai(
            {"verb": "GetRecord", "metadataPrefix": "mets", "identifier": identifier}
        )
        return self._with_bitstreams(book, mets, file_limit=file_limit)
