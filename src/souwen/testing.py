"""Testing helpers for SouWen adapters."""

from __future__ import annotations

import inspect
import logging
from souwen.registry.adapter import SourceAdapter

logger = logging.getLogger("souwen.testing")


def validate_client_contract(adapter: SourceAdapter) -> list[str]:
    """Deep-validate an adapter's lazy client contract where importable."""
    issues: list[str] = []

    if not callable(adapter.client_loader):
        return [f"Adapter {adapter.name!r} client_loader must be callable."]

    try:
        client_cls = adapter.client_loader()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Skipping client contract validation for adapter %r: %s",
            adapter.name,
            exc,
        )
        return issues

    if not inspect.isclass(client_cls):
        issues.append(f"Adapter {adapter.name!r} client_loader must return a client class.")
        return issues

    for method_name in ("__aenter__", "__aexit__"):
        if not hasattr(client_cls, method_name):
            issues.append(f"Client class for adapter {adapter.name!r} must define {method_name}.")

    for capability, method_spec in adapter.methods.items():
        if not hasattr(client_cls, method_spec.method_name):
            issues.append(
                f"Client class for adapter {adapter.name!r} must define method "
                f"{method_spec.method_name!r} for capability {capability!r}."
            )

    return issues


__all__ = ["validate_client_contract"]
