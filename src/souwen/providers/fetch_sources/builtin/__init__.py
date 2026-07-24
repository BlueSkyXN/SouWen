"""Builtin canonical Fetch Provider v2 adapter."""

from .adapter import BuiltinFetchProvider, LegacyBuiltinFetchClientProtocol
from .manifest import BUILTIN_FETCH_MANIFEST

__all__ = ["BUILTIN_FETCH_MANIFEST", "BuiltinFetchProvider", "LegacyBuiltinFetchClientProtocol"]
