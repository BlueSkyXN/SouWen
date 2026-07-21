"""Project Gutenberg official RDF catalog importer and local-book adapter.

The canonical bulk input is the official daily RDF archive.  The same parser
accepts an official per-record RDF file for bounded live validation; neither
path follows declared ebook/resource URLs.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from defusedxml import ElementTree as ET

from souwen.config import get_config
from souwen.core.exceptions import LocalCatalogUnavailableError, ParseError
from souwen.models import (
    Author,
    BookIdentifier,
    BookResult,
    ResourceAccess,
    ResourceLink,
    SearchResponse,
)
from souwen.local_catalog.store import CatalogRecord, LocalCatalog

SOURCE = "gutenberg"
CANONICAL_RDF_ARCHIVE_URL = "https://www.gutenberg.org/cache/epub/feeds/rdf-files.tar.bz2"
LIVE_SAMPLE_RDF_URL = "https://www.gutenberg.org/cache/epub/11/pg11.rdf"
_ALLOWED_DOWNLOAD_URLS = frozenset({CANONICAL_RDF_ARCHIVE_URL, LIVE_SAMPLE_RDF_URL})
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_MAX_RDF_MEMBER_BYTES = 5 * 1024 * 1024
_MAX_TOTAL_RDF_BYTES = 2 * 1024 * 1024 * 1024
_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dcterms": "http://purl.org/dc/terms/",
    "pgterms": "http://www.gutenberg.org/2009/pgterms/",
    "dcam": "http://purl.org/dc/dcam/",
}
_RDF_ABOUT = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about"
_RDF_RESOURCE = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"
_XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _values(root: ET.Element, path: str) -> list[str]:
    return [value for item in root.findall(path, _NS) if (value := _text(item))]


def _gutenberg_id(value: str | None) -> str:
    if not value:
        return ""
    suffix = value.rstrip("/").rsplit("/", 1)[-1]
    return suffix if suffix.isdigit() and int(suffix) > 0 else ""


def _as_https_gutenberg_url(value: str, base: str) -> str:
    resolved = urljoin(base, value)
    parsed = urlparse(resolved)
    if parsed.scheme == "http" and parsed.hostname and parsed.hostname.endswith("gutenberg.org"):
        return parsed._replace(scheme="https").geturl()
    return resolved


def _is_official_gutenberg_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname in {"www.gutenberg.org", "gutenberg.org"}


def _sha256_file(path: Path) -> tuple[str, int]:
    """Return an observed file digest without loading a bulk catalog into memory."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as input_file:
        while chunk := input_file.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _resource_access(rights: str | None, license_url: str | None) -> ResourceAccess:
    is_us_public_domain = bool(rights and rights.strip().lower() == "public domain in the usa.")
    return ResourceAccess(
        status="public_domain" if is_us_public_domain else "metadata_only",
        rights=rights,
        license_url=license_url,
        region="US" if is_us_public_domain else None,
        notes=(
            "Source-declared Gutenberg rights; availability and redistribution outside the United States "
            "are not verified. Declared resource URLs are not fetched."
        ),
    )


def parse_gutenberg_rdf(data: bytes, *, input_sha256: str) -> CatalogRecord:
    """Parse one official Gutenberg RDF/XML record without requesting formats."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError("Gutenberg RDF is invalid XML") from exc
    ebook = root.find(".//pgterms:ebook", _NS)
    if ebook is None:
        raise ParseError("Gutenberg RDF has no pgterms:ebook")
    record_id = _gutenberg_id(ebook.get(_RDF_ABOUT))
    title = _text(ebook.find("dcterms:title", _NS))
    if not record_id or not title:
        raise ParseError("Gutenberg RDF lacks ebook ID or title")
    base = root.get(_XML_BASE) or "https://www.gutenberg.org/"
    rights = _text(ebook.find("dcterms:rights", _NS))
    license_node = ebook.find("dcterms:license", _NS)
    license_ref = license_node.get(_RDF_RESOURCE) if license_node is not None else None
    license_url = _as_https_gutenberg_url(license_ref, base) if license_ref else None
    access = _resource_access(rights, license_url)
    authors = [Author(name=value) for value in _values(ebook, "dcterms:creator//pgterms:name")]
    contributors = [
        Author(name=value) for value in _values(ebook, "dcterms:contributor//pgterms:name")
    ]
    languages = _values(ebook, "dcterms:language//rdf:value")
    publishers = _values(ebook, "dcterms:publisher")
    descriptions = _values(ebook, "dcterms:description")
    subjects: list[str] = []
    structured_subjects: list[dict[str, str | None]] = []
    for subject in ebook.findall("dcterms:subject", _NS):
        value = _text(subject.find(".//rdf:value", _NS))
        if value is None:
            continue
        scheme_node = subject.find(".//dcam:memberOf", _NS)
        scheme = scheme_node.get(_RDF_RESOURCE) if scheme_node is not None else None
        subjects.append(value)
        structured_subjects.append({"value": value, "scheme": scheme})
    collections = _values(ebook, "pgterms:bookshelf//rdf:value")
    files: list[dict[str, object]] = []
    resources: list[ResourceLink] = []
    for node in ebook.findall("dcterms:hasFormat//pgterms:file", _NS):
        url = node.get(_RDF_ABOUT)
        if not url:
            continue
        mime = _text(node.find("dcterms:format//rdf:value", _NS))
        extent = _text(node.find("dcterms:extent", _NS))
        modified = _text(node.find("dcterms:modified", _NS))
        try:
            size_bytes = int(extent) if extent is not None and int(extent) >= 0 else None
        except ValueError:
            size_bytes = None
        resolved_url = _as_https_gutenberg_url(url, base)
        resources.append(
            ResourceLink(
                url=resolved_url,
                relation="declared_format",
                label="Project Gutenberg declared format metadata",
                size_bytes=size_bytes,
                media_type=mime,
                format=mime,
                source=SOURCE,
                access=access.model_copy(deep=True),
            )
        )
        files.append(
            {
                "url": resolved_url,
                "media_type": mime,
                "size_bytes": size_bytes,
                "modified": modified,
            }
        )
    issued = _text(ebook.find("dcterms:issued", _NS))
    book = BookResult(
        source=SOURCE,
        source_record_id=record_id,
        title=title,
        authors=authors,
        contributors=contributors,
        languages=languages,
        subjects=subjects,
        collections=collections,
        publishers=publishers,
        description=descriptions[0] if descriptions else None,
        identifiers=[BookIdentifier(scheme="source_record_id", value=record_id)],
        resources=resources,
        access=access,
        source_url=f"https://www.gutenberg.org/ebooks/{record_id}",
    )
    return CatalogRecord(
        book=book,
        metadata={
            "canonical_format": "project_gutenberg_rdf_xml",
            "record_sha256": hashlib.sha256(data).hexdigest(),
            "input_sha256": input_sha256,
            "gutenberg_release_date": issued,
            "subjects": structured_subjects,
            "files": files,
            "license_url": license_url,
            "rights": rights,
        },
    )


def iter_gutenberg_rdf_records(path: Path, *, input_sha256: str) -> Iterable[CatalogRecord]:
    """Yield records from one official RDF file or a safe RDF tar.bz2 archive."""
    if path.suffix == ".rdf":
        yield parse_gutenberg_rdf(path.read_bytes(), input_sha256=input_sha256)
        return
    try:
        with tarfile.open(path, "r:bz2") as archive:
            total_rdf_bytes = 0
            for member in archive:
                if member.issym() or member.islnk():
                    raise ParseError("Gutenberg RDF archive contains a link member")
                if member.name.startswith("/") or ".." in Path(member.name).parts:
                    raise ParseError("Gutenberg RDF archive contains an unsafe member path")
                if not member.isfile():
                    continue
                if not member.name.endswith(".rdf"):
                    continue
                if member.size > _MAX_RDF_MEMBER_BYTES:
                    raise ParseError("Gutenberg RDF archive contains an oversized RDF member")
                total_rdf_bytes += member.size
                if total_rdf_bytes > _MAX_TOTAL_RDF_BYTES:
                    raise ParseError("Gutenberg RDF archive exceeds total extraction safety limit")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ParseError("Gutenberg RDF archive member is unreadable")
                yield parse_gutenberg_rdf(stream.read(), input_sha256=input_sha256)
    except tarfile.TarError as exc:
        raise ParseError("Gutenberg canonical input must be RDF/XML or RDF tar.bz2") from exc


@dataclass(frozen=True, slots=True)
class DownloadReceipt:
    path: Path
    url: str
    content_length: int | None
    last_modified: str | None
    sha256: str
    retrieved_at: str


def download_official_gutenberg_catalog(url: str, destination: Path) -> DownloadReceipt:
    """Download an official catalog file through a same-filesystem temporary path."""
    if url not in _ALLOWED_DOWNLOAD_URLS:
        raise ValueError("Gutenberg URL must be the canonical RDF archive or bounded RDF sample")
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    part.unlink(missing_ok=True)
    request = Request(url, headers={"User-Agent": "SouWen local catalog importer"})
    try:
        with urlopen(request, timeout=60) as response, part.open("wb") as output:  # nosec B310: host is allowlisted
            final_url = response.geturl()
            if not _is_official_gutenberg_url(final_url):
                raise ParseError("Gutenberg catalog redirect left the official host")
            content_length = response.headers.get("Content-Length")
            expected = int(content_length) if content_length and content_length.isdigit() else None
            if expected is not None and expected > _MAX_ARCHIVE_BYTES:
                raise ParseError("Gutenberg catalog exceeds local importer safety limit")
            digest = hashlib.sha256()
            received = 0
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > _MAX_ARCHIVE_BYTES:
                    raise ParseError("Gutenberg catalog exceeds local importer safety limit")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
            if expected is not None and received != expected:
                raise ParseError("Gutenberg catalog content length mismatch")
            last_modified = response.headers.get("Last-Modified")
        os.replace(part, destination)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return DownloadReceipt(
        destination,
        final_url,
        expected,
        last_modified,
        digest.hexdigest(),
        datetime.now(timezone.utc).isoformat(),
    )


def import_gutenberg_input(
    catalog: LocalCatalog,
    path: Path,
    *,
    resume: bool = False,
    replace_source: bool = False,
    acquisition: Mapping[str, object] | None = None,
) -> dict[str, int]:
    """Import an official RDF input; the file itself is never an ebook body."""
    digest, observed_size = _sha256_file(path)
    records = iter_gutenberg_rdf_records(path, input_sha256=digest)
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


class GutenbergLocalCatalogClient:
    """Registry adapter client that queries only the initialized local SQLite catalog."""

    def __init__(self) -> None:
        self._catalog = LocalCatalog(get_config().local_catalog_db_path)

    async def __aenter__(self) -> "GutenbergLocalCatalogClient":
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

    async def get_by_id(self, gutenberg_id: str) -> BookResult:
        return await asyncio.to_thread(self._catalog.get_book, SOURCE, gutenberg_id)


def gutenberg_catalog_ready() -> bool:
    """Return local readiness without leaking the configured filesystem path."""
    try:
        LocalCatalog(get_config().local_catalog_db_path).ensure_source_ready(SOURCE)
    except LocalCatalogUnavailableError:
        return False
    return True
