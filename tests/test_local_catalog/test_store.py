from __future__ import annotations

import sqlite3

import pytest

from souwen.core.exceptions import LocalCatalogUnavailableError
from souwen.local_catalog.store import CatalogRecord, LocalCatalog
from souwen.models import BookResult


def _record(
    record_id: str, title: str = "Alice", *, subjects: list[str] | None = None
) -> CatalogRecord:
    return CatalogRecord(
        BookResult(
            source="gutenberg",
            source_record_id=record_id,
            title=title,
            subjects=subjects or ["Fiction"],
            source_url=f"https://www.gutenberg.org/ebooks/{record_id}",
        ),
        {"record": record_id},
    )


def test_fresh_db_idempotent_update_delete_fts_and_integrity(tmp_path) -> None:
    catalog = LocalCatalog(tmp_path / "catalog.sqlite3")
    assert catalog.status().initialized is False
    assert catalog.import_records("gutenberg", "r1", "a" * 64, [_record("11")]) == {
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "deleted": 0,
    }
    assert catalog.status().integrity == "ok"
    assert [
        book.source_record_id for book in catalog.search_books("gutenberg", "Alice", limit=10)
    ] == ["11"]
    assert catalog.import_records("gutenberg", "r1", "a" * 64, [_record("11")])["unchanged"] == 1
    assert (
        catalog.import_records("gutenberg", "r2", "b" * 64, [_record("11", "Alice revised")])[
            "updated"
        ]
        == 1
    )
    assert catalog.get_book("gutenberg", "11").title == "Alice revised"
    catalog.import_records(
        "gutenberg", "r3", "c" * 64, [_record("12", "Other")], replace_source=True
    )
    with pytest.raises(Exception):
        catalog.get_book("gutenberg", "11")
    assert catalog.get_book("gutenberg", "12").title == "Other"


def test_empty_uninitialized_future_schema_and_failed_run_are_explicit(tmp_path) -> None:
    path = tmp_path / "catalog.sqlite3"
    catalog = LocalCatalog(path)
    with pytest.raises(LocalCatalogUnavailableError, match="not initialized"):
        catalog.search_books("gutenberg", "Alice", limit=1)
    catalog.initialize()
    with pytest.raises(LocalCatalogUnavailableError, match="no completed"):
        catalog.search_books("gutenberg", "Alice", limit=1)
    with pytest.raises(ValueError, match="不一致"):
        catalog.import_records(
            "gutenberg",
            "bad",
            "d" * 64,
            [
                _record("11"),
                CatalogRecord(_record("12").book.model_copy(update={"source": "cbeta"}), {}),
            ],
        )
    assert catalog.status().completed_imports == {}
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM catalog_schema_version")
        conn.execute("INSERT INTO catalog_schema_version VALUES (999, 'now')")
    with pytest.raises(LocalCatalogUnavailableError, match="not supported"):
        catalog.initialize()


def test_fts_unavailable_is_not_silently_accepted(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(LocalCatalog, "_fts5_available", staticmethod(lambda _conn: False))
    with pytest.raises(LocalCatalogUnavailableError, match="FTS5"):
        LocalCatalog(tmp_path / "catalog.sqlite3").initialize()
