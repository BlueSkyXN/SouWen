"""Shared doctor response builder for user/admin routes."""

from __future__ import annotations

from typing import Any


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
    return {
        **counts,
        "edition": get_config().edition,
        "probe_mode": "live" if live else "static",
        "live_probe": summarize_live_probes(results) if live else None,
        "sources": results,
    }
