"""Versioned SQLite storage for source-provenanced local catalog records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from souwen.core.exceptions import LocalCatalogUnavailableError, NotFoundError
from souwen.models import BookResult

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    """One normalized record plus importer-only structured provenance."""

    book: BookResult
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class CatalogStatus:
    path: Path
    initialized: bool
    schema_version: int | None
    fts5_available: bool
    integrity: str | None
    source_counts: dict[str, int]
    completed_imports: dict[str, int]
    latest_imports: dict[str, dict[str, object]]


class LocalCatalog:
    """SQLite catalog with explicit schema, FTS5 and import-run boundaries."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def _connect(self, *, create: bool) -> sqlite3.Connection:
        if not create and not self.path.is_file():
            raise LocalCatalogUnavailableError("local catalog is not initialized")
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self, *, create: bool) -> Iterator[sqlite3.Connection]:
        """Commit or roll back a catalog operation and always release its SQLite handle."""
        conn = self._connect(create=create)
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _fts5_available(conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _catalog_fts_probe USING fts5(value)")
            conn.execute("DROP TABLE _catalog_fts_probe")
            return True
        except sqlite3.OperationalError:
            return False

    def initialize(self) -> CatalogStatus:
        with self._connection(create=True) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='catalog_schema_version'"
            ).fetchone()
            if row is not None:
                version = conn.execute(
                    "SELECT MAX(version) FROM catalog_schema_version"
                ).fetchone()[0]
                if version != SCHEMA_VERSION:
                    raise LocalCatalogUnavailableError(
                        f"local catalog schema version {version} is not supported"
                    )
            else:
                if not self._fts5_available(conn):
                    raise LocalCatalogUnavailableError("SQLite FTS5 is unavailable")
                conn.executescript(
                    """
                    CREATE TABLE catalog_schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
                    INSERT INTO catalog_schema_version VALUES (1, CURRENT_TIMESTAMP);
                    CREATE TABLE catalog_records (
                      source TEXT NOT NULL, source_record_id TEXT NOT NULL, payload_json TEXT NOT NULL,
                      metadata_json TEXT NOT NULL, source_revision TEXT NOT NULL, input_sha256 TEXT NOT NULL,
                      updated_at TEXT NOT NULL, PRIMARY KEY(source, source_record_id)
                    );
                    CREATE TABLE catalog_import_runs (
                      source TEXT NOT NULL, source_revision TEXT NOT NULL, input_sha256 TEXT NOT NULL,
                      acquisition_json TEXT NOT NULL DEFAULT '{}',
                      status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
                      checkpoint INTEGER NOT NULL DEFAULT 0, inserted_count INTEGER NOT NULL DEFAULT 0,
                      updated_count INTEGER NOT NULL DEFAULT 0, unchanged_count INTEGER NOT NULL DEFAULT 0,
                      deleted_count INTEGER NOT NULL DEFAULT 0, started_at TEXT NOT NULL, finished_at TEXT,
                      error_message TEXT, PRIMARY KEY(source, source_revision)
                    );
                    CREATE VIRTUAL TABLE catalog_book_fts USING fts5(record_key UNINDEXED, title, authors, subjects);
                    """
                )
        return self.status()

    def status(self) -> CatalogStatus:
        if not self.path.is_file():
            return CatalogStatus(self.path, False, None, False, None, {}, {}, {})
        try:
            with self._connection(create=False) as conn:
                row = conn.execute(
                    "SELECT MAX(version) AS version FROM catalog_schema_version"
                ).fetchone()
                version = row["version"] if row else None
                counts = {
                    row["source"]: row["count"]
                    for row in conn.execute(
                        "SELECT source, COUNT(*) AS count FROM catalog_records GROUP BY source"
                    )
                }
                completed = {
                    row["source"]: row["count"]
                    for row in conn.execute(
                        "SELECT source, COUNT(*) AS count FROM catalog_import_runs "
                        "WHERE status='completed' GROUP BY source"
                    )
                }
                latest_imports: dict[str, dict[str, object]] = {}
                for import_row in conn.execute(
                    "SELECT source,source_revision,input_sha256,acquisition_json,status,checkpoint,"
                    "inserted_count,updated_count,unchanged_count,deleted_count,started_at,finished_at "
                    "FROM catalog_import_runs ORDER BY started_at DESC"
                ):
                    if import_row["source"] in latest_imports:
                        continue
                    try:
                        acquisition = json.loads(import_row["acquisition_json"])
                    except (TypeError, json.JSONDecodeError):
                        acquisition = {}
                    latest_imports[import_row["source"]] = {
                        "source_revision": import_row["source_revision"],
                        "input_sha256": import_row["input_sha256"],
                        "acquisition": acquisition,
                        "status": import_row["status"],
                        "checkpoint": import_row["checkpoint"],
                        "inserted": import_row["inserted_count"],
                        "updated": import_row["updated_count"],
                        "unchanged": import_row["unchanged_count"],
                        "deleted": import_row["deleted_count"],
                        "started_at": import_row["started_at"],
                        "finished_at": import_row["finished_at"],
                    }
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                return CatalogStatus(
                    self.path,
                    True,
                    version,
                    self._fts5_available(conn),
                    integrity,
                    counts,
                    completed,
                    latest_imports,
                )
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as exc:
            raise LocalCatalogUnavailableError("local catalog is unreadable") from exc

    def ensure_source_ready(self, source: str) -> None:
        status = self.status()
        if not status.initialized:
            raise LocalCatalogUnavailableError("local catalog is not initialized")
        if status.schema_version != SCHEMA_VERSION or not status.fts5_available:
            raise LocalCatalogUnavailableError("local catalog runtime requirements are unavailable")
        if status.integrity != "ok":
            raise LocalCatalogUnavailableError("local catalog integrity check failed")
        if not status.completed_imports.get(source) or not status.source_counts.get(source):
            raise LocalCatalogUnavailableError(f"local catalog has no completed {source} import")

    @staticmethod
    def _fts_query(query: str) -> str:
        terms = [term.replace('"', '""') for term in query.split() if term]
        if not terms:
            raise ValueError("query 必须非空")
        return " AND ".join(f'"{term}"' for term in terms)

    def search_books(self, source: str, query: str, *, limit: int) -> list[BookResult]:
        self.ensure_source_ready(source)
        if not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1..100")
        with self._connection(create=False) as conn:
            rows = conn.execute(
                "SELECT r.payload_json FROM catalog_book_fts f JOIN catalog_records r "
                "ON f.record_key = r.source || ':' || r.source_record_id "
                "WHERE catalog_book_fts MATCH ? AND r.source=? ORDER BY rank LIMIT ?",
                (self._fts_query(query), source, limit),
            ).fetchall()
        return [BookResult.model_validate_json(row["payload_json"]) for row in rows]

    def get_book(self, source: str, source_record_id: str) -> BookResult:
        self.ensure_source_ready(source)
        with self._connection(create=False) as conn:
            row = conn.execute(
                "SELECT payload_json FROM catalog_records WHERE source=? AND source_record_id=?",
                (source, source_record_id),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"local catalog record not found: {source_record_id}")
        return BookResult.model_validate_json(row["payload_json"])

    def import_records(
        self,
        source: str,
        source_revision: str,
        input_sha256: str,
        records: Iterable[CatalogRecord],
        *,
        resume: bool = False,
        replace_source: bool = False,
        acquisition: Mapping[str, object] | None = None,
    ) -> dict[str, int]:
        """Upsert records and preserve a checkpoint after every committed record."""
        self.initialize()
        acquisition_json = json.dumps(dict(acquisition or {}), ensure_ascii=False, sort_keys=True)
        with self._connection(create=False) as conn:
            previous = conn.execute(
                "SELECT * FROM catalog_import_runs WHERE source=? AND source_revision=?",
                (source, source_revision),
            ).fetchone()
            checkpoint = (
                int(previous["checkpoint"])
                if previous and previous["status"] == "failed" and resume
                else 0
            )
            counters = {
                "inserted": int(previous["inserted_count"]) if checkpoint else 0,
                "updated": int(previous["updated_count"]) if checkpoint else 0,
                "unchanged": int(previous["unchanged_count"]) if checkpoint else 0,
                "deleted": 0,
            }
            conn.execute(
                "INSERT INTO catalog_import_runs(source,source_revision,input_sha256,acquisition_json,status,checkpoint,inserted_count,updated_count,unchanged_count,deleted_count,started_at) "
                "VALUES (?,?,?,?,'running',?,?,?,?,0,?) ON CONFLICT(source,source_revision) DO UPDATE SET "
                "input_sha256=excluded.input_sha256,acquisition_json=excluded.acquisition_json,status='running',checkpoint=excluded.checkpoint,inserted_count=excluded.inserted_count,updated_count=excluded.updated_count,unchanged_count=excluded.unchanged_count,deleted_count=0,started_at=excluded.started_at,finished_at=NULL,error_message=NULL",
                (
                    source,
                    source_revision,
                    input_sha256,
                    acquisition_json,
                    checkpoint,
                    counters["inserted"],
                    counters["updated"],
                    counters["unchanged"],
                    _now(),
                ),
            )
            conn.commit()
            try:
                imported_ids: set[str] = set()
                for index, record in enumerate(records, start=1):
                    book = record.book
                    if book.source != source:
                        raise ValueError("catalog record source 与 import source 不一致")
                    imported_ids.add(book.source_record_id)
                    if index <= checkpoint:
                        continue
                    # ``retrieved_at`` describes the local normalization moment, not the
                    # upstream record.  It must not turn an identical reimport into an update.
                    payload = book.model_copy(update={"retrieved_at": None}).model_dump_json(
                        exclude_none=True
                    )
                    metadata = json.dumps(record.metadata, ensure_ascii=False, sort_keys=True)
                    existing = conn.execute(
                        "SELECT payload_json,metadata_json FROM catalog_records WHERE source=? AND source_record_id=?",
                        (source, book.source_record_id),
                    ).fetchone()
                    kind = (
                        "inserted"
                        if existing is None
                        else "unchanged"
                        if existing["payload_json"] == payload
                        and existing["metadata_json"] == metadata
                        else "updated"
                    )
                    counters[kind] += 1
                    conn.execute(
                        "INSERT INTO catalog_records VALUES (?,?,?,?,?,?,?) ON CONFLICT(source,source_record_id) DO UPDATE SET payload_json=excluded.payload_json,metadata_json=excluded.metadata_json,source_revision=excluded.source_revision,input_sha256=excluded.input_sha256,updated_at=excluded.updated_at",
                        (
                            source,
                            book.source_record_id,
                            payload,
                            metadata,
                            source_revision,
                            input_sha256,
                            _now(),
                        ),
                    )
                    key = f"{source}:{book.source_record_id}"
                    conn.execute("DELETE FROM catalog_book_fts WHERE record_key=?", (key,))
                    conn.execute(
                        "INSERT INTO catalog_book_fts VALUES (?,?,?,?)",
                        (
                            key,
                            book.title,
                            " ".join(a.name for a in book.authors),
                            " ".join(book.subjects),
                        ),
                    )
                    conn.execute(
                        "UPDATE catalog_import_runs SET checkpoint=?,inserted_count=?,updated_count=?,unchanged_count=? WHERE source=? AND source_revision=?",
                        (
                            index,
                            counters["inserted"],
                            counters["updated"],
                            counters["unchanged"],
                            source,
                            source_revision,
                        ),
                    )
                    conn.commit()
                if replace_source:
                    # Deletion is only valid after the complete input iterator finished
                    # successfully; a parser/interruption failure leaves existing records intact.
                    stale = conn.execute(
                        "SELECT source_record_id FROM catalog_records WHERE source=?", (source,)
                    ).fetchall()
                    stale_ids = [
                        row["source_record_id"]
                        for row in stale
                        if row["source_record_id"] not in imported_ids
                    ]
                    for record_id in stale_ids:
                        conn.execute(
                            "DELETE FROM catalog_book_fts WHERE record_key=?",
                            (f"{source}:{record_id}",),
                        )
                        conn.execute(
                            "DELETE FROM catalog_records WHERE source=? AND source_record_id=?",
                            (source, record_id),
                        )
                    counters["deleted"] = len(stale_ids)
                conn.execute(
                    "UPDATE catalog_import_runs SET status='completed',deleted_count=?,finished_at=?,error_message=NULL WHERE source=? AND source_revision=?",
                    (counters["deleted"], _now(), source, source_revision),
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                conn.execute(
                    "UPDATE catalog_import_runs SET status='failed',finished_at=?,error_message=? WHERE source=? AND source_revision=?",
                    (_now(), type(exc).__name__, source, source_revision),
                )
                conn.commit()
                raise
        return counters
