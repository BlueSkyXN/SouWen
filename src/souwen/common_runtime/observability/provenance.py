"""Runtime source provenance resolution.

The resolver reads immutable build provenance without owning deployment policy or
mutating runtime state.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

SOURCE_SHA_ENV = "SOUWEN_SOURCE_SHA"
SOURCE_SHA_FILE_ENV = "SOUWEN_SOURCE_SHA_FILE"
SOURCE_SHA_FILENAME = "runtime.source.sha"
_FULL_SHA = re.compile(r"^[0-9a-fA-F]{40}$")


def _normalize_source_sha(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not _FULL_SHA.fullmatch(candidate):
        return None
    return candidate.lower()


def _default_source_sha_files() -> Iterator[Path]:
    seen: set[Path] = set()
    candidates = [Path.cwd() / SOURCE_SHA_FILENAME]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / SOURCE_SHA_FILENAME)
    candidates.append(Path(sys.executable).resolve().parent / SOURCE_SHA_FILENAME)
    module_path = Path(__file__).resolve()
    candidates.extend(
        (
            module_path.parents[3] / SOURCE_SHA_FILENAME,
            module_path.parents[4] / SOURCE_SHA_FILENAME,
        )
    )

    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            yield candidate


def _read_source_sha_file(path: Path) -> str | None:
    try:
        return _normalize_source_sha(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def get_source_sha() -> str | None:
    """Return a validated 40-character Git SHA for the running artifact."""
    direct = os.environ.get(SOURCE_SHA_ENV)
    if direct is not None:
        return _normalize_source_sha(direct)

    explicit_file = os.environ.get(SOURCE_SHA_FILE_ENV)
    if explicit_file is not None:
        return _read_source_sha_file(Path(explicit_file).expanduser())

    for path in _default_source_sha_files():
        source_sha = _read_source_sha_file(path)
        if source_sha is not None:
            return source_sha
    return None


__all__ = [
    "SOURCE_SHA_ENV",
    "SOURCE_SHA_FILE_ENV",
    "SOURCE_SHA_FILENAME",
    "get_source_sha",
]
