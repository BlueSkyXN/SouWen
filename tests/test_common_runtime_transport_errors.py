"""Canonical Common Runtime error identity and hierarchy tests."""

from __future__ import annotations

import ast
from pathlib import Path

from souwen.common_runtime import errors as canonical_errors
from souwen.common_runtime.transport import (
    AuthError,
    RateLimitError,
    SourceUnavailableError,
    SouWenError,
)
from souwen.common_runtime.transport import errors as canonical_transport_errors
from souwen.core import exceptions as legacy_errors
from souwen.core import http_client, retry


def test_legacy_transport_errors_reexport_canonical_objects() -> None:
    assert legacy_errors.SouWenError is SouWenError
    assert legacy_errors.AuthError is AuthError
    assert legacy_errors.RateLimitError is RateLimitError
    assert legacy_errors.SourceUnavailableError is SourceUnavailableError
    assert SouWenError.__module__ == "souwen.common_runtime.errors"
    assert AuthError.__module__ == "souwen.common_runtime.transport.errors"
    assert RateLimitError.__module__ == "souwen.common_runtime.transport.errors"
    assert SourceUnavailableError.__module__ == "souwen.common_runtime.transport.errors"


def test_domain_specific_legacy_errors_preserve_canonical_hierarchy() -> None:
    assert issubclass(legacy_errors.ConfigError, SouWenError)
    assert issubclass(legacy_errors.ParseError, SouWenError)
    assert issubclass(legacy_errors.NotFoundError, SouWenError)
    assert issubclass(legacy_errors.LocalCatalogUnavailableError, SourceUnavailableError)

    try:
        raise legacy_errors.ConfigError("example_key", "Example")
    except SouWenError as exc:
        assert exc.key == "example_key"

    try:
        raise legacy_errors.LocalCatalogUnavailableError("catalog unavailable")
    except SourceUnavailableError as exc:
        assert str(exc) == "catalog unavailable"


def test_http_and_retry_consumers_use_canonical_error_identity() -> None:
    assert http_client.SouWenError is SouWenError
    assert http_client.AuthError is AuthError
    assert http_client.RateLimitError is RateLimitError
    assert http_client.SourceUnavailableError is SourceUnavailableError
    assert retry.RateLimitError is RateLimitError
    assert retry.SourceUnavailableError is SourceUnavailableError


def test_rate_limit_error_contract_is_preserved() -> None:
    error = RateLimitError("限流触发", retry_after=2.5)

    assert isinstance(error, SouWenError)
    assert str(error) == "限流触发"
    assert error.retry_after == 2.5
    default_error = RateLimitError()
    assert str(default_error) == "请求过于频繁"
    assert default_error.retry_after is None


def test_canonical_error_modules_have_no_legacy_or_domain_dependencies() -> None:
    for module, allowed_imports in (
        (canonical_errors, set()),
        (canonical_transport_errors, {"souwen.common_runtime.errors"}),
    ):
        path = Path(module.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert imported == allowed_imports


def test_legacy_module_defines_only_domain_specific_error_classes() -> None:
    path = Path(legacy_errors.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    defined_classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}

    assert defined_classes == {
        "ConfigError",
        "LocalCatalogUnavailableError",
        "NotFoundError",
        "ParseError",
    }
