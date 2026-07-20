"""Shared doctor response builder for user/admin routes."""

from __future__ import annotations

import re
from typing import Any


def _sanitize_rest_live_probe(probe: dict[str, Any]) -> dict[str, Any]:
    """Keep live probe outcomes truthful without echoing provider exception text."""

    sanitized = dict(probe)
    status = str(probe.get("status") or "")
    message = str(probe.get("message") or "")
    if status == "failed":
        if re.fullmatch(r"timed out after \d+(?:\.\d+)?s", message):
            return sanitized
        sanitized["message"] = (
            "rate limited" if message.startswith("rate limited:") else "live probe failed"
        )
    elif status == "skipped" and message.startswith("missing config:"):
        sanitized["message"] = "missing configuration"
    return sanitized


def _sanitize_rest_runtime_details(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy REST doctor rows while redacting arbitrary loader exception text."""

    from souwen.feature_matrix import RuntimeProbe, sanitize_public_runtime_probe

    sanitized_results: list[dict[str, Any]] = []
    for item in results:
        sanitized = dict(item)
        raw_reason = str(item.get("runtime_reason") or "")
        runtime = sanitize_public_runtime_probe(
            str(item.get("name") or "source"),
            RuntimeProbe(bool(item.get("runtime_available")), raw_reason),
        )
        if runtime.reason != raw_reason:
            sanitized["runtime_reason"] = runtime.reason
            message = sanitized.get("message")
            if raw_reason and isinstance(message, str) and raw_reason in message:
                sanitized["message"] = message.replace(raw_reason, runtime.reason)
        live_probe = sanitized.get("live_probe")
        if isinstance(live_probe, dict):
            sanitized["live_probe"] = _sanitize_rest_live_probe(live_probe)
        sanitized_results.append(sanitized)
    return sanitized_results


async def build_doctor_payload(
    *,
    live: bool = False,
    sources: list[str] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Build the source status summary used by doctor endpoints."""
    from souwen.config import get_config
    from souwen.doctor import (
        check_all,
        check_all_live,
        summarize_live_probes,
        summarize_statuses,
    )

    results = await check_all_live(sources=sources, timeout=timeout) if live else check_all()
    counts = summarize_statuses(results)
    response_results = _sanitize_rest_runtime_details(results)
    return {
        **counts,
        "edition": get_config().edition,
        "probe_mode": "live" if live else "static",
        "live_probe": summarize_live_probes(results) if live else None,
        "sources": response_results,
    }
