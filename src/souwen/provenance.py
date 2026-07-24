"""Compatibility imports for runtime source provenance.

New internal consumers use :mod:`souwen.common_runtime.observability`; this
module preserves the established import path during the Phase 3 migration.
"""

from souwen.common_runtime.observability.provenance import (
    SOURCE_SHA_ENV,
    SOURCE_SHA_FILE_ENV,
    SOURCE_SHA_FILENAME,
    get_source_sha,
)

__all__ = [
    "SOURCE_SHA_ENV",
    "SOURCE_SHA_FILE_ENV",
    "SOURCE_SHA_FILENAME",
    "get_source_sha",
]
