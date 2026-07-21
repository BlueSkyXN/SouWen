"""Taiwan National Central Library new-books CSV importer.

The public data.gov.tw dataset publishes monthly ISBN application metadata.  It
is catalog metadata only: this importer neither follows nor creates full-text
links.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import os
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from io import TextIOWrapper
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from souwen.config import get_config
from souwen.core.exceptions import LocalCatalogUnavailableError, ParseError
from souwen.local_catalog.gutenberg import DownloadReceipt, _sha256_file
from souwen.local_catalog.store import CatalogRecord, LocalCatalog
from souwen.models import Author, BookIdentifier, BookResult, ResourceAccess, SearchResponse

SOURCE = "taiwan_new_books"
DATA_GOV_DATASET_ID = 6730
DATA_GOV_DETAIL_URL = f"https://data.gov.tw/api/front/dataset/detail?nid={DATA_GOV_DATASET_ID}"
_ALLOWED_RESOURCE_HOSTS = frozenset({"www.ncl.edu.tw", "isbn.ncl.edu.tw"})
_REQUIRED_COLUMNS = frozenset({"申請書名", "作者", "出版機構", "ISBN"})
_MAX_CSV_BYTES = 64 * 1024 * 1024


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _isbn(value: str | None) -> str | None:
    value = "".join(char for char in (value or "") if char.isdigit() or char in "Xx")
    if len(value) in {10, 13}:
        return value.upper()
    return None


def _authors(value: str | None) -> list[Author]:
    if not (value := _clean(value)):
        return []
    return [Author(name=name) for name in value.replace("；", ";").split(";") if name.strip()]


def _year(value: str | None) -> int | None:
    value = _clean(value)
    if not value:
        return None
    for token in value.replace("/", "-").split("-"):
        if len(token) == 4 and token.isdigit() and 1900 <= int(token) <= 2100:
            return int(token)
    return None


def _metadata_access() -> ResourceAccess:
    return ResourceAccess(
        status="metadata_only",
        notes="Official Taiwan new-books ISBN application metadata only; no full-text access or reuse right is implied.",
    )


def parse_taiwan_new_books_csv(stream: BinaryIO, *, input_sha256: str) -> Iterable[CatalogRecord]:
    """Parse the declared UTF-8 CSV and skip rows without a stable ISBN identity."""
    reader = csv.DictReader(TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
    if not reader.fieldnames or not _REQUIRED_COLUMNS.issubset(reader.fieldnames):
        raise ParseError("Taiwan new-books CSV header is incompatible with the official dataset")
    for row in reader:
        isbn = _isbn(row.get("ISBN"))
        title = _clean(row.get("申請書名"))
        if not isbn or not title:
            continue
        language = _clean(row.get("作品語文"))
        classification = _clean(row.get("分類號"))
        subjects = [value for value in (_clean(row.get("圖書主題")), classification) if value]
        book = BookResult(
            source=SOURCE,
            source_record_id=isbn,
            title=title,
            authors=_authors(row.get("作者")),
            languages=[language] if language else [],
            subjects=subjects,
            publishers=[publisher] if (publisher := _clean(row.get("出版機構"))) else [],
            first_publish_year=_year(row.get("預訂出版日")),
            identifiers=[
                BookIdentifier(scheme="isbn13" if len(isbn) == 13 else "isbn10", value=isbn)
            ],
            access=_metadata_access(),
            source_url=DATA_GOV_DETAIL_URL,
        )
        yield CatalogRecord(
            book=book,
            metadata={
                "canonical_format": "taiwan_ncl_new_books_csv",
                "input_sha256": input_sha256,
                "edition": _clean(row.get("版次")),
                "planned_publication_date": _clean(row.get("預訂出版日")),
                "classification": classification,
                "price": _clean(row.get("定價")),
                "format": _clean(row.get("出版形式")),
                "language_other": _clean(row.get("作品語文(其他)")),
                "source_row_sha256": hashlib.sha256(
                    repr(sorted(row.items())).encode("utf-8")
                ).hexdigest(),
            },
        )


def import_taiwan_new_books_input(
    catalog: LocalCatalog,
    path: Path,
    *,
    resume: bool = False,
    replace_source: bool = False,
    acquisition: Mapping[str, object] | None = None,
) -> dict[str, int]:
    digest, observed_size = _sha256_file(path)
    with path.open("rb") as stream:
        records = list(parse_taiwan_new_books_csv(stream, input_sha256=digest))
    evidence = {
        "input_kind": "local_file",
        "observed_sha256": digest,
        "observed_size_bytes": observed_size,
    }
    if acquisition:
        evidence.update(acquisition)
    return catalog.import_records(
        SOURCE,
        digest,
        digest,
        records,
        resume=resume,
        replace_source=replace_source,
        acquisition=evidence,
    )


def _is_official_resource_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in _ALLOWED_RESOURCE_HOSTS


def download_official_taiwan_new_books_csv(url: str, destination: Path) -> DownloadReceipt:
    """Download one URL declared by the official dataset, with redirect host validation."""
    if not _is_official_resource_url(url):
        raise ValueError("Taiwan new-books URL must be an official NCL HTTPS resource")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    part.unlink(missing_ok=True)
    request = Request(url, headers={"User-Agent": "SouWen local catalog importer"})
    try:
        with urlopen(request, timeout=60) as response, part.open("wb") as output:  # nosec B310: host allowlisted
            final_url = response.geturl()
            if not _is_official_resource_url(final_url):
                raise ParseError("Taiwan new-books resource redirect left the official NCL host")
            digest = hashlib.sha256()
            received = 0
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > _MAX_CSV_BYTES:
                    raise ParseError("Taiwan new-books CSV exceeds local importer safety limit")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        os.replace(part, destination)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return DownloadReceipt(
        destination,
        final_url,
        received,
        None,
        digest.hexdigest(),
        datetime.now(timezone.utc).isoformat(),
    )


class TaiwanNewBooksLocalCatalogClient:
    def __init__(self) -> None:
        self._catalog = LocalCatalog(get_config().local_catalog_db_path)

    async def __aenter__(self) -> "TaiwanNewBooksLocalCatalogClient":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def search(self, query: str, per_page: int = 10) -> SearchResponse:
        results = await asyncio.to_thread(self._catalog.search_books, SOURCE, query, limit=per_page)
        return SearchResponse(
            query=query,
            source=SOURCE,
            total_results=len(results),
            results=results,
            per_page=per_page,
        )

    async def get_by_id(self, isbn: str) -> BookResult:
        return await asyncio.to_thread(self._catalog.get_book, SOURCE, isbn)


def taiwan_new_books_catalog_ready() -> bool:
    try:
        LocalCatalog(get_config().local_catalog_db_path).ensure_source_ready(SOURCE)
    except LocalCatalogUnavailableError:
        return False
    return True
