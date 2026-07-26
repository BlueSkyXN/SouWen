"""Deterministic registry, configuration, and local-runtime diagnostics."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from souwen.common_runtime.observability import get_source_sha
from souwen.config import get_config
from souwen.core.exceptions import ConfigError, RateLimitError
from souwen.feature_matrix import probe_adapter_runtime
from souwen.registry.catalog import source_catalog
from souwen.registry.meta import (
    INTEGRATION_TYPE_LABELS,
    OPTIONAL_CREDENTIAL_EFFECT_LABELS,
    credential_fields_label,
    has_required_credentials,
    missing_credential_fields,
    source_config_validation_reason,
)
from souwen.registry.views import get as get_adapter

_INTEGRATION_TYPE_ORDER = ("open_api", "scraper", "official_api", "self_hosted")
_STATUS_ICONS = {
    "ok": "✅",
    "warning": "⚠️",
    "limited": "⚠️",
    "unavailable": "❌",
    "missing_key": "⬜",
    "disabled": "🚫",
}
AVAILABLE_STATUSES = frozenset({"ok", "limited", "warning", "degraded"})
DEGRADED_STATUSES = frozenset({"limited", "warning", "degraded"})
LIVE_PROBE_QUERY = "machine learning"
LIVE_PROBE_TIMEOUT_SECONDS = 5.0


def is_available_status(status: str | None) -> bool:
    return status in AVAILABLE_STATUSES


def summarize_statuses(results: list[dict]) -> dict[str, int | dict[str, int]]:
    counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    total = len(results)
    available = sum(counts.get(status, 0) for status in AVAILABLE_STATUSES)
    degraded = sum(counts.get(status, 0) for status in DEGRADED_STATUSES)
    return {
        "total": total,
        "ok": counts.get("ok", 0),
        "available": available,
        "degraded": degraded,
        "degraded_total": degraded,
        "failed": total - available,
        "limited": counts.get("limited", 0),
        "warning": counts.get("warning", 0),
        "missing_key": counts.get("missing_key", 0),
        "unavailable": counts.get("unavailable", 0),
        "disabled": counts.get("disabled", 0),
        "status_counts": counts,
    }


def summarize_live_probes(results: list[dict]) -> dict[str, int | dict[str, int]]:
    counts: dict[str, int] = {}
    total = 0
    for result in results:
        probe = result.get("live_probe")
        if not isinstance(probe, dict):
            continue
        total += 1
        status = str(probe.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "total": total,
        "ok": counts.get("ok", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "status_counts": counts,
    }


def _optional_credential_message(meta: Any, configured: bool) -> tuple[str, str]:
    fields = credential_fields_label(meta.credential_fields)
    if not fields:
        return "ok", "免配置可用"
    if configured:
        return "ok", f"{fields} 已配置"
    effect = OPTIONAL_CREDENTIAL_EFFECT_LABELS.get(
        meta.optional_credential_effect or "unknown", "增强能力"
    )
    return "limited", f"免配置可用；设置 {fields} 可{effect}"


def _stability_status(meta: Any) -> tuple[str, str] | None:
    if meta.stability == "deprecated":
        return "unavailable", meta.usage_note or f"{meta.name} 当前接入待修复"
    if meta.stability == "experimental" and meta.integration_type == "scraper":
        return "warning", meta.usage_note or "实验性爬虫，可能受反爬或 HTML 变更影响"
    return None


def check_all() -> list[dict]:
    """Report registry sources without network, browser, or credential probes."""

    config = get_config()
    results: list[dict] = []
    for name, meta in source_catalog().items():
        adapter = get_adapter(name)
        if adapter is None:  # pragma: no cover - catalog and registry are co-derived.
            raise KeyError(f"missing registry adapter for source {name!r}")
        enabled = config.is_source_enabled(name, default=adapter.runtime_default_enabled)
        runtime = probe_adapter_runtime(adapter)
        missing = missing_credential_fields(config, name, meta)
        credentials_satisfied = has_required_credentials(config, name, meta)
        validation_reason = source_config_validation_reason(config, name, meta)
        config_available = enabled and credentials_satisfied and not validation_reason
        if not enabled:
            status, message, config_reason = (
                "disabled",
                "已通过频道配置禁用",
                "disabled by source configuration",
            )
        elif validation_reason:
            status, message, config_reason = "unavailable", validation_reason, validation_reason
        elif not runtime.available:
            status, message, config_reason = "unavailable", runtime.reason, ""
        else:
            config_reason = ""
            stability = _stability_status(meta)
            if stability is not None:
                status, message = stability
            elif meta.auth_requirement == "none":
                status, message = "ok", "免配置；未做实时可用性探测"
            elif meta.auth_requirement == "optional":
                status, message = _optional_credential_message(meta, not missing)
            elif credentials_satisfied:
                status, message = "ok", f"{credential_fields_label(meta.credential_fields)} 已配置"
            else:
                status, message = (
                    "missing_key",
                    f"需要设置 {credential_fields_label(tuple(missing))}",
                )
            if meta.usage_note and meta.usage_note not in message:
                message = f"{message}（{meta.usage_note}）"
        channel: dict[str, str] = {}
        source_config = config.get_source_config(name)
        if source_config.proxy != "inherit":
            channel["proxy"] = source_config.proxy
        if source_config.http_backend != "auto":
            channel["http_backend"] = source_config.http_backend
        if source_config.timeout is not None:
            channel["timeout"] = str(source_config.timeout)
        results.append(
            {
                "name": name,
                "category": meta.category,
                "status": status,
                "integration_type": meta.integration_type,
                "required_key": meta.config_field,
                "key_requirement": meta.auth_requirement,
                "auth_requirement": meta.auth_requirement,
                "credential_fields": list(meta.credential_fields),
                "optional_credential_effect": meta.optional_credential_effect,
                "risk_level": meta.risk_level,
                "risk_reasons": sorted(meta.risk_reasons),
                "distribution": meta.distribution,
                "package_extra": meta.package_extra,
                "stability": meta.stability,
                "usage_note": meta.usage_note,
                "runtime_available": runtime.available,
                "runtime_reason": runtime.reason,
                "credentials_satisfied": credentials_satisfied,
                "missing_credential_fields": missing,
                "config_valid": not validation_reason,
                "config_available": config_available,
                "config_reason": config_reason,
                "available": runtime.available and config_available and is_available_status(status),
                "message": message,
                "enabled": enabled,
                "description": meta.description,
                "channel": channel or None,
            }
        )
    return results


def check_capabilities() -> dict[str, Any]:
    """Return source, package, LLM, and WARP capability diagnostics."""

    from souwen.feature_matrix import (
        LLM_PROVIDER_MODULES,
        WARP_MODE_NAMES,
        probe_capabilities,
        probe_modules,
        probe_results_to_dict,
    )

    llm_runtime = probe_modules(LLM_PROVIDER_MODULES.values())
    return {
        "source_sha": get_source_sha(),
        "sources": summarize_statuses(check_all()),
        "warp_modes": list(WARP_MODE_NAMES),
        "llm": {
            "runtime_available": llm_runtime.available,
            "runtime_reason": llm_runtime.reason,
        },
        "probe": probe_results_to_dict(probe_capabilities()),
    }


def _source_names_filter(sources: list[str] | str | None) -> set[str] | None:
    if sources is None:
        return None
    if isinstance(sources, str):
        sources = [sources]
    return {item.strip() for item in sources if item.strip()}


def _live_probe_skipped(message: str) -> dict[str, Any]:
    return {"status": "skipped", "message": message, "elapsed_ms": 0}


async def _live_probe_source(item: dict, *, query: str, timeout: float) -> dict[str, Any]:
    if not item.get("enabled"):
        return _live_probe_skipped("source is disabled")
    if not item.get("available"):
        return _live_probe_skipped(f"static status is {item.get('status')}")
    adapter = get_adapter(str(item["name"]))
    if adapter is None or "search" not in adapter.capabilities:
        return _live_probe_skipped("source does not expose search capability")
    from souwen.search import _run_via_adapter

    started = time.monotonic()

    def elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        response = await asyncio.wait_for(
            _run_via_adapter(adapter, "search", query=query, limit=1), timeout=timeout
        )
    except ConfigError as exc:
        return {
            "status": "skipped",
            "message": f"missing config: {exc}",
            "elapsed_ms": elapsed_ms(),
        }
    except RateLimitError as exc:
        return {
            "status": "failed",
            "message": f"rate limited: {exc}",
            "elapsed_ms": elapsed_ms(),
        }
    except asyncio.TimeoutError:
        return {
            "status": "failed",
            "message": f"timed out after {timeout:g}s",
            "elapsed_ms": elapsed_ms(),
        }
    except Exception as exc:  # noqa: BLE001 - live diagnostics report rather than raise.
        return {
            "status": "failed",
            "message": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": elapsed_ms(),
        }
    if getattr(response, "error", None):
        return {"status": "failed", "message": str(response.error), "elapsed_ms": elapsed_ms()}
    return {"status": "ok", "message": "live search returned", "elapsed_ms": elapsed_ms()}


async def check_all_live(
    *,
    sources: list[str] | str | None = None,
    query: str = LIVE_PROBE_QUERY,
    timeout: float = LIVE_PROBE_TIMEOUT_SECONDS,
) -> list[dict]:
    """Attach opt-in bounded live probes to static doctor results."""

    results = check_all()
    selected = _source_names_filter(sources)
    targets = [item for item in results if selected is None or item["name"] in selected]
    probes = await asyncio.gather(
        *[_live_probe_source(item, query=query, timeout=max(0.5, timeout)) for item in targets]
    )
    for item, probe in zip(targets, probes, strict=True):
        item["live_probe"] = probe
    return results


def format_report(results: list[dict]) -> str:
    counts = summarize_statuses(results)
    lines = [
        "🩺 SouWen Doctor — 数据源健康检查",
        f"   {counts['available']}/{counts['total']} 个数据源可用\n",
    ]
    by_type: dict[str, list[dict]] = {kind: [] for kind in _INTEGRATION_TYPE_ORDER}
    for result in results:
        by_type.setdefault(str(result["integration_type"]), []).append(result)
    for kind in _INTEGRATION_TYPE_ORDER:
        items = by_type[kind]
        if not items:
            continue
        available = sum(is_available_status(item["status"]) for item in items)
        lines.append(f"── {INTEGRATION_TYPE_LABELS.get(kind, kind)} ({available}/{len(items)}) ──")
        for item in items:
            lines.append(
                f"  {_STATUS_ICONS.get(item['status'], '•')} {item['name']:<20} {item['message']}"
            )
    return "\n".join(lines)
