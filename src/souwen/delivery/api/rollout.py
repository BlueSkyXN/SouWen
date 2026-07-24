"""Deployment-scoped RC2 rollout mode and target route ownership."""

from __future__ import annotations

import os
from enum import Enum


class RolloutMode(str, Enum):
    LEGACY = "legacy"
    TARGET = "target"


_TARGET_DATA_PATHS = frozenset(
    {
        "/api/v1/search",
        "/api/v1/llm-search",
        "/api/v1/fetch",
        "/api/v1/providers",
    }
)
_TARGET_PROBE_PATHS = frozenset({"/health", "/healthz", "/readiness", "/readyz"})


def resolve_rollout_mode(value: str | None = None) -> RolloutMode:
    raw = os.environ.get("SOUWEN_V2_ROLLOUT", "legacy") if value is None else value
    normalized = raw.strip().lower()
    try:
        return RolloutMode(normalized)
    except ValueError:
        raise ValueError("SOUWEN_V2_ROLLOUT must be exactly 'legacy' or 'target'") from None


def is_target_contract_path(path: str, mode: RolloutMode) -> bool:
    return path in _TARGET_PROBE_PATHS or (
        mode is RolloutMode.TARGET and path in _TARGET_DATA_PATHS
    )


__all__ = ["RolloutMode", "is_target_contract_path", "resolve_rollout_mode"]
