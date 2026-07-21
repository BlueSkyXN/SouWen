# local_catalog navigation card

Type: Domain card.
This package owns the persistent local SQLite catalog, import-run provenance,
FTS capability checks and source-specific bulk importers.

## Local invariants

- Keep this database physically separate from `session_cache.db`.
- Records are unique by stable `(source, source_record_id)` and imports are
  idempotent; never fabricate a successful import after a partial failure.
- Every importer stores source revision and acquisition evidence. Resource URLs
  are metadata only and must never be followed during normal import.
- SQLite schema version, FTS5 support and `PRAGMA integrity_check` are runtime
  contracts, not assumptions based on the Python dependency set.

## Do not

- Do not import ebook bodies when official catalog metadata suffices.
- Do not use third-party mirrors in place of an official bulk/feed contract.
- Do not silently accept a future schema version or fall back from FTS to an
  incompatible search semantic.

## Validation

- `pytest tests/test_local_catalog -v --tb=short`
- Run the relevant functional check fixture mode; live mode is always explicit.
