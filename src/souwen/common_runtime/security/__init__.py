"""Security runtime boundary. Owner: Common Runtime. Allowed dependencies: standard library and common runtime."""

from .fetch_target import ResolvedFetchTarget, resolve_fetch_target, validate_fetch_url

__all__ = ["ResolvedFetchTarget", "resolve_fetch_target", "validate_fetch_url"]
