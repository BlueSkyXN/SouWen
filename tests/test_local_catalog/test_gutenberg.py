from __future__ import annotations

import asyncio
import io
import tarfile
from email.message import Message

import pytest

from souwen.local_catalog import LocalCatalog
from souwen.local_catalog.gutenberg import (
    GutenbergLocalCatalogClient,
    download_official_gutenberg_catalog,
    import_gutenberg_input,
    iter_gutenberg_rdf_records,
    parse_gutenberg_rdf,
)

_RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:pgterms="http://www.gutenberg.org/2009/pgterms/" xmlns:dcam="http://purl.org/dc/dcam/" xml:base="http://www.gutenberg.org/">
  <pgterms:ebook rdf:about="ebooks/11">
    <dcterms:title>Alice's Adventures in Wonderland</dcterms:title>
    <dcterms:creator><pgterms:agent><pgterms:name>Carroll, Lewis</pgterms:name></pgterms:agent></dcterms:creator>
    <dcterms:language><rdf:Description><rdf:value>en</rdf:value></rdf:Description></dcterms:language>
    <dcterms:subject><rdf:Description><rdf:value>Children's fiction</rdf:value><dcam:memberOf rdf:resource="http://purl.org/dc/terms/LCSH"/></rdf:Description></dcterms:subject>
    <pgterms:bookshelf><rdf:Description><rdf:value>Children's Literature</rdf:value></rdf:Description></pgterms:bookshelf>
    <dcterms:publisher>Project Gutenberg</dcterms:publisher>
    <dcterms:issued>2008-06-27</dcterms:issued>
    <dcterms:rights>Public domain in the USA.</dcterms:rights>
    <dcterms:license rdf:resource="license"/>
    <dcterms:hasFormat><pgterms:file rdf:about="https://www.gutenberg.org/ebooks/11.epub3.images"><dcterms:format><rdf:Description><rdf:value>application/epub+zip</rdf:value></rdf:Description></dcterms:format><dcterms:extent>189196</dcterms:extent><dcterms:modified>2026-06-01T03:31:55Z</dcterms:modified></pgterms:file></dcterms:hasFormat>
  </pgterms:ebook>
</rdf:RDF>"""


def test_parse_preserves_official_rdf_metadata_without_following_resource_urls() -> None:
    record = parse_gutenberg_rdf(_RDF, input_sha256="a" * 64)
    book = record.book
    assert book.source_record_id == "11"
    assert book.title == "Alice's Adventures in Wonderland"
    assert book.authors[0].name == "Carroll, Lewis"
    assert book.languages == ["en"]
    assert book.access.region == "US"
    assert book.resources[0].url == "https://www.gutenberg.org/ebooks/11.epub3.images"
    assert book.resources[0].size_bytes == 189196
    assert record.metadata["gutenberg_release_date"] == "2008-06-27"
    assert record.metadata["files"][0]["modified"] == "2026-06-01T03:31:55Z"


def test_local_rdf_import_and_adapter_query(tmp_path, monkeypatch) -> None:
    path = tmp_path / "pg11.rdf"
    path.write_bytes(_RDF)
    db_path = tmp_path / "catalog.sqlite3"
    catalog = LocalCatalog(db_path)
    counters = import_gutenberg_input(
        catalog,
        path,
        acquisition={"url": "https://www.gutenberg.org/cache/epub/11/pg11.rdf"},
    )
    assert counters["inserted"] == 1
    latest = catalog.status().latest_imports["gutenberg"]
    assert latest["status"] == "completed"
    assert latest["acquisition"]["observed_sha256"]
    assert latest["acquisition"]["url"].endswith("/pg11.rdf")
    monkeypatch.setenv("SOUWEN_LOCAL_CATALOG_PATH", str(db_path))

    async def run() -> None:
        async with GutenbergLocalCatalogClient() as client:
            response = await client.search("Alice", per_page=5)
            assert response.results[0].source_record_id == "11"
            assert (await client.get_by_id("11")).title.startswith("Alice")

    asyncio.run(run())


def test_invalid_rdf_does_not_create_completed_import(tmp_path) -> None:
    path = tmp_path / "bad.rdf"
    path.write_text("<not-rdf>", encoding="utf-8")
    catalog = LocalCatalog(tmp_path / "catalog.sqlite3")
    with pytest.raises(Exception):
        import_gutenberg_input(catalog, path)
    assert catalog.status().completed_imports == {}
    assert catalog.status().latest_imports["gutenberg"]["status"] == "failed"


def test_archive_rejects_link_and_path_traversal_members(tmp_path) -> None:
    archive_path = tmp_path / "catalog.tar.bz2"
    with tarfile.open(archive_path, "w:bz2") as archive:
        link = tarfile.TarInfo("records/link.rdf")
        link.type = tarfile.SYMTYPE
        link.linkname = "elsewhere.rdf"
        archive.addfile(link)
    with pytest.raises(Exception, match="link member"):
        list(iter_gutenberg_rdf_records(archive_path, input_sha256="a" * 64))

    with tarfile.open(archive_path, "w:bz2") as archive:
        record = tarfile.TarInfo("../escape.rdf")
        record.size = len(_RDF)
        archive.addfile(record, io.BytesIO(_RDF))
    with pytest.raises(Exception, match="unsafe member path"):
        list(iter_gutenberg_rdf_records(archive_path, input_sha256="a" * 64))


def test_download_rejects_redirect_official_host_escape_and_removes_partial_file(
    tmp_path, monkeypatch
) -> None:
    class RedirectedResponse:
        headers = Message()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self) -> str:
            return "https://unexpected.example/catalog.rdf"

        def read(self, _size: int) -> bytes:
            return b""

    monkeypatch.setattr(
        "souwen.local_catalog.gutenberg.urlopen", lambda *_args, **_kwargs: RedirectedResponse()
    )
    destination = tmp_path / "pg11.rdf"
    with pytest.raises(Exception, match="left the official host"):
        download_official_gutenberg_catalog(
            "https://www.gutenberg.org/cache/epub/11/pg11.rdf", destination
        )
    assert not destination.exists()
    assert not destination.with_suffix(".rdf.part").exists()


def test_download_rejects_non_rdf_official_url_before_network(tmp_path) -> None:
    with pytest.raises(Exception, match="canonical RDF archive or bounded RDF sample"):
        download_official_gutenberg_catalog(
            "https://www.gutenberg.org/ebooks/11.epub3.images", tmp_path / "unexpected.epub"
        )
