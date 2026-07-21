from __future__ import annotations

import asyncio
from io import BytesIO

from souwen.local_catalog import LocalCatalog
from souwen.local_catalog.taiwan_new_books import (
    SOURCE,
    TaiwanNewBooksLocalCatalogClient,
    import_taiwan_new_books_input,
    parse_taiwan_new_books_csv,
)


_CSV = """申請書名,作者,出版機構,版次,預訂出版日,分類號,ISBN,作品語文,圖書主題,定價,出版形式
測試新書,王小明；李小華,測試出版社,初版,2026-07-01,800,978-986-12345-6-7,中文,資訊科學,450,平裝
沒有 ISBN 的資料,王小明,測試出版社,初版,2026-07-01,800,,中文,資訊科學,450,平裝
""".encode()


def test_parse_maps_metadata_only_book_and_skips_missing_isbn() -> None:
    records = list(parse_taiwan_new_books_csv(BytesIO(_CSV), input_sha256="a" * 64))

    assert len(records) == 1
    record = records[0]
    assert record.book.source == SOURCE
    assert record.book.source_record_id == "9789861234567"
    assert record.book.title == "測試新書"
    assert [author.name for author in record.book.authors] == ["王小明", "李小華"]
    assert record.book.identifiers[0].scheme == "isbn13"
    assert record.book.access.status == "metadata_only"
    assert record.book.first_publish_year == 2026
    assert record.metadata["edition"] == "初版"
    assert record.metadata["classification"] == "800"


def test_import_is_idempotent_and_adapter_queries_local_catalog(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "new-books.csv"
    input_path.write_bytes(_CSV)
    catalog = LocalCatalog(tmp_path / "catalog.sqlite3")

    assert import_taiwan_new_books_input(catalog, input_path)["inserted"] == 1
    assert import_taiwan_new_books_input(catalog, input_path)["unchanged"] == 1
    monkeypatch.setenv("SOUWEN_LOCAL_CATALOG_PATH", str(catalog.path))

    async def run() -> None:
        async with TaiwanNewBooksLocalCatalogClient() as client:
            result = await client.search("測試新書", per_page=5)
            assert result.results[0].source_record_id == "9789861234567"
            assert (await client.get_by_id("9789861234567")).title == "測試新書"

    asyncio.run(run())
