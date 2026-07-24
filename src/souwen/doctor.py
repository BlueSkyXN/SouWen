"""SouWen 数据源健康检查

文件用途：
    检测所有已注册数据源的可用性状态（配置、依赖、服务），
    按集成类型（integration_type）分组并生成用户友好的报告。

函数清单：
    check_all() -> list[dict]
        - 功能：检查所有数据源的可用性，返回详细检查结果
        - 返回：每个数据源一条字典
        - 字典字段：name (源名称), category (分类), status (状态),
                   integration_type (集成类型), required_key (配置字段),
                   message (状态说明), enabled (启用状态),
                   min_edition / edition_available / edition_reason,
                   runtime_available / runtime_reason,
                   config_available / config_reason / available,
                   description (源描述), channel (频道配置摘要)
        - 检测逻辑：
          * 首先检查频道配置是否禁用
          * 然后检查特定源的特殊条件（Key 配置、curl_cffi 依赖等）
          * 最后收集频道配置（代理、HTTP 后端、自定义 URL）

    format_report(results: list[dict]) -> str
        - 功能：将 check_all() 结果格式化为可读报告（Markdown 风格）
        - 返回：包含摘要、集成类型分组、每个源状态的格式化字符串
        - 输出格式：Emoji 图标 + 源名称 + 分类标签 + 状态说明

状态枚举（status 字段）：
    "ok" (✅) — 正常可用（配置完整或无需配置）
    "warning" (⚠️) — 警告（如爬虫缺少 curl_cffi，但仍可尝试）
    "limited" (⚠️) — 受限（如无 API Key 的 Semantic Scholar 易限流）
    "unavailable" (❌) — 不可用（接入待修复 / 已下线等）
    "missing_key" (⬜) — 缺少必要配置
    "disabled" (🚫) — 用户手动禁用

模块依赖：
    - souwen.config: 配置管理、源启用状态检查
    - souwen.registry.meta: 获取所有注册源、元数据、集成类型标签
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from souwen.config import get_config
from souwen.core.exceptions import ConfigError, RateLimitError
from souwen.editions import (
    EDITIONS,
    FULL_WARP_MODES,
    PREINSTALLED_PLUGIN_MODULES,
    edition_policy,
    fetch_provider_policy,
    source_policy,
    warp_mode_policy,
)
from souwen.feature_matrix import RuntimeProbe, probe_adapter_runtime
from souwen.common_runtime.observability import get_source_sha
from souwen.registry.catalog import source_catalog
from souwen.registry.meta import (
    AUTH_REQUIREMENT_LABELS,
    INTEGRATION_TYPE_LABELS,
    OPTIONAL_CREDENTIAL_EFFECT_LABELS,
    credential_fields_label,
    get_source,
    has_required_credentials,
    is_llm_search_gateway_requirement,
    missing_credential_fields,
    source_config_validation_reason,
)
from souwen.registry.views import get as get_adapter

# 集成类型分组的展示顺序
_INTEGRATION_TYPE_ORDER = ("open_api", "scraper", "official_api", "self_hosted")

_STATUS_ICONS = {
    "ok": "✅",
    "warning": "⚠️",
    "limited": "⚠️",
    "unavailable": "❌",
    "missing_key": "⬜",
    "disabled": "🚫",
}

_LIMITED_OPTIONAL_EFFECTS = {
    "rate_limit",
    "quota",
    "quality",
    "personalization",
    "private_access",
}

AVAILABLE_STATUSES = frozenset({"ok", "limited", "warning", "degraded"})
DEGRADED_STATUSES = frozenset({"limited", "warning", "degraded"})
LIVE_PROBE_QUERY = "machine learning"
LIVE_PROBE_TIMEOUT_SECONDS = 5.0


def is_available_status(status: str | None) -> bool:
    """判断 doctor 状态是否仍可用。"""
    return status in AVAILABLE_STATUSES


def summarize_statuses(results: list[dict]) -> dict[str, int | dict[str, int]]:
    """汇总 doctor 状态，区分严格 ok、可用、降级总数与失败。"""
    status_counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    total = len(results)
    available = sum(status_counts.get(status, 0) for status in AVAILABLE_STATUSES)
    degraded_total = sum(status_counts.get(status, 0) for status in DEGRADED_STATUSES)
    failed = total - available
    return {
        "total": total,
        "ok": status_counts.get("ok", 0),
        "available": available,
        "degraded": degraded_total,
        "degraded_total": degraded_total,
        "failed": failed,
        "limited": status_counts.get("limited", 0),
        "warning": status_counts.get("warning", 0),
        "missing_key": status_counts.get("missing_key", 0),
        "unavailable": status_counts.get("unavailable", 0),
        "disabled": status_counts.get("disabled", 0),
        "status_counts": status_counts,
    }


def summarize_live_probes(results: list[dict]) -> dict[str, int | dict[str, int]]:
    """Summarize optional live connectivity probe results."""

    status_counts: dict[str, int] = {}
    total = 0
    for result in results:
        probe = result.get("live_probe")
        if not isinstance(probe, dict):
            continue
        total += 1
        status = str(probe.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "total": total,
        "ok": status_counts.get("ok", 0),
        "failed": status_counts.get("failed", 0),
        "skipped": status_counts.get("skipped", 0),
        "status_counts": status_counts,
    }


def _empty_edition_buckets() -> dict[str, dict[str, int]]:
    return {
        edition: {
            "total": 0,
            "edition_available": 0,
            "edition_unavailable": 0,
            "runtime_available": 0,
            "config_available": 0,
            "available": 0,
        }
        for edition in EDITIONS
    }


def _summarize_edition_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总一组带 min_edition / edition_available / available 的能力项。"""

    buckets = _empty_edition_buckets()
    upgrade_required: list[dict[str, str]] = []
    missing_runtime: list[dict[str, str]] = []
    missing_config: list[dict[str, str]] = []
    edition_available_count = 0
    runtime_available_count = 0
    config_available_count = 0
    available_count = 0

    for item in items:
        min_edition = str(item["min_edition"])
        bucket = buckets[min_edition]
        bucket["total"] += 1

        if bool(item.get("edition_available")):
            bucket["edition_available"] += 1
            edition_available_count += 1
        else:
            bucket["edition_unavailable"] += 1
            upgrade_required.append(
                {
                    "name": str(item["name"]),
                    "min_edition": min_edition,
                    "reason": str(item.get("edition_reason") or item.get("reason") or ""),
                }
            )

        if bool(item.get("runtime_available")):
            bucket["runtime_available"] += 1
            runtime_available_count += 1
        else:
            missing_runtime.append(
                {
                    "name": str(item["name"]),
                    "min_edition": min_edition,
                    "reason": str(item.get("runtime_reason") or "runtime unavailable"),
                }
            )

        if bool(item.get("config_available", True)):
            bucket["config_available"] += 1
            config_available_count += 1
        else:
            missing_config.append(
                {
                    "name": str(item["name"]),
                    "min_edition": min_edition,
                    "reason": str(item.get("config_reason") or "configuration unavailable"),
                }
            )

        if bool(item.get("available")):
            bucket["available"] += 1
            available_count += 1

    total = len(items)
    return {
        "total": total,
        "edition_available": edition_available_count,
        "edition_unavailable": total - edition_available_count,
        "runtime_available": runtime_available_count,
        "runtime_unavailable": total - runtime_available_count,
        "config_available": config_available_count,
        "config_unavailable": total - config_available_count,
        "available": available_count,
        "by_min_edition": buckets,
        "upgrade_required": upgrade_required,
        "missing_runtime": missing_runtime,
        "missing_config": missing_config,
    }


def _format_name_list(items: list[dict[str, Any]] | list[str], *, limit: int = 12) -> str:
    if not items:
        return "-"
    names = [str(item["name"] if isinstance(item, dict) else item) for item in items]
    if len(names) <= limit:
        return ", ".join(names)
    return f"{', '.join(names[:limit])}, ... (+{len(names) - limit})"


def check_edition() -> dict[str, Any]:
    """返回当前 edition 的能力自检报告。

    该报告不做真实联网探测；它汇总当前 registry、source doctor 状态、
    fetch provider policy、WARP mode policy、LLM policy 和预装插件探测结果。
    """

    cfg = get_config()
    source_results = check_all()
    source_items = [
        {
            "name": str(item["name"]),
            "min_edition": str(item["min_edition"]),
            "edition_available": bool(item["edition_available"]),
            "edition_reason": str(item.get("edition_reason") or ""),
            "runtime_available": bool(item["runtime_available"]),
            "runtime_reason": str(item.get("runtime_reason") or ""),
            "config_available": bool(item["config_available"]),
            "config_reason": str(item.get("config_reason") or ""),
            "available": bool(item["available"]),
        }
        for item in source_results
    ]
    source_summary = _summarize_edition_items(source_items)
    source_summary["items"] = source_items
    source_summary["status_counts"] = summarize_statuses(source_results)

    from souwen.feature_matrix import (
        LLM_PROVIDER_MODULES,
        probe_adapter_runtime,
        probe_capabilities,
        probe_modules,
        probe_results_to_dict,
    )
    from souwen.registry import fetch_providers

    fetch_items: list[dict[str, Any]] = []
    for adapter in sorted(fetch_providers(), key=lambda item: item.name):
        policy = fetch_provider_policy(adapter, cfg.edition)
        runtime = probe_adapter_runtime(adapter)
        meta = get_source(adapter.name)
        enabled = cfg.is_source_enabled(adapter.name, default=adapter.runtime_default_enabled)
        credentials_satisfied = (
            has_required_credentials(cfg, adapter.name, meta) if meta is not None else True
        )
        config_available = enabled and credentials_satisfied
        if not enabled:
            config_reason = "disabled by source configuration"
        elif not credentials_satisfied:
            missing = missing_credential_fields(cfg, adapter.name, meta)
            config_reason = (
                f"missing configuration: {credential_fields_label(tuple(missing))}"
                if missing
                else "required configuration is missing"
            )
        else:
            config_reason = ""
        fetch_items.append(
            {
                "name": adapter.name,
                "min_edition": policy.min_edition,
                "edition_available": policy.available,
                "edition_reason": policy.reason,
                "runtime_available": runtime.available,
                "runtime_reason": runtime.reason,
                "config_available": config_available,
                "config_reason": config_reason,
                "credentials_satisfied": credentials_satisfied,
                "enabled": enabled,
                "available": policy.available and runtime.available and config_available,
            }
        )
    fetch_summary = _summarize_edition_items(fetch_items)
    fetch_summary["items"] = fetch_items

    warp_modes: list[dict[str, Any]] = []
    for mode in FULL_WARP_MODES:
        policy = warp_mode_policy(mode, cfg.edition)
        warp_modes.append(
            {
                "name": mode,
                "min_edition": policy.min_edition,
                "edition_available": policy.available,
                "edition_reason": policy.reason,
                "runtime_available": True,
                "runtime_reason": "",
                "config_available": True,
                "config_reason": "",
                "available": policy.available,
            }
        )

    llm_policy = edition_policy("LLM", current=cfg.edition, required="pro")
    plugin_policy = edition_policy(
        "preinstalled plugin packages",
        current=cfg.edition,
        required="full",
    )
    llm_runtime = probe_modules(LLM_PROVIDER_MODULES.values())
    plugin_runtime = probe_modules(PREINSTALLED_PLUGIN_MODULES)
    plugin_importable = plugin_runtime.available
    probe = probe_results_to_dict(probe_capabilities(cfg.edition))

    return {
        "edition": cfg.edition,
        "source_sha": get_source_sha(),
        "sources": source_summary,
        "fetch_providers": fetch_summary,
        "warp": {
            "modes": warp_modes,
            "available_modes": [mode["name"] for mode in warp_modes if mode["available"]],
            "upgrade_required": [mode for mode in warp_modes if not mode["edition_available"]],
        },
        "llm": {
            "min_edition": llm_policy.min_edition,
            "edition_available": llm_policy.available,
            "edition_reason": llm_policy.reason,
            "runtime_available": llm_runtime.available,
            "runtime_reason": llm_runtime.reason,
            "available": llm_policy.available and llm_runtime.available,
        },
        "plugins": {
            "min_edition": plugin_policy.min_edition,
            "edition_available": plugin_policy.available,
            "edition_reason": plugin_policy.reason,
            "preinstalled": plugin_importable,
            "runtime_available": plugin_runtime.available,
            "runtime_reason": plugin_runtime.reason,
            "available": plugin_policy.available and plugin_runtime.available,
            "candidate_modules": list(PREINSTALLED_PLUGIN_MODULES),
        },
        "probe": probe,
    }


def format_edition_report(report: dict[str, Any] | None = None) -> str:
    """格式化 ``check_edition()`` 的自检报告。"""

    data = report or check_edition()
    edition = str(data["edition"])
    sources = data["sources"]
    fetch = data["fetch_providers"]
    warp = data["warp"]
    llm = data["llm"]
    plugins = data["plugins"]
    probe = data.get("probe") if isinstance(data.get("probe"), dict) else {}
    package_extras = (
        probe.get("package_extras")
        if isinstance(probe, dict) and isinstance(probe.get("package_extras"), dict)
        else {}
    )
    extra_declared = package_extras.get("declared") if isinstance(package_extras, dict) else {}
    extra_available = package_extras.get("available") if isinstance(package_extras, dict) else ()
    extra_reason = (
        str(package_extras.get("reason") or "") if isinstance(package_extras, dict) else ""
    )
    extra_names = sorted(extra_declared) if isinstance(extra_declared, dict) else []
    available_extras = list(extra_available) if isinstance(extra_available, (list, tuple)) else []

    lines: list[str] = [
        f"🧭 SouWen Doctor — Edition 自检 (edition={edition})",
        f"  source_sha={data.get('source_sha') or 'unavailable'}",
        "",
        "── Sources ──",
        (
            f"  {sources['edition_available']}/{sources['total']} 个 source 当前 edition 允许；"
            f"{sources['runtime_available']} 个 runtime 可加载；"
            f"{sources['config_available']} 个配置满足；{sources['available']} 个最终可用"
        ),
    ]
    for bucket, counts in sources["by_min_edition"].items():
        lines.append(
            f"  min={bucket}: {counts['edition_available']}/{counts['total']} edition 允许；"
            f"{counts['runtime_available']} runtime 可加载；{counts['available']} 最终可用"
        )
    if sources["upgrade_required"]:
        lines.append(f"  需升级 source: {_format_name_list(sources['upgrade_required'])}")
    if sources["missing_runtime"]:
        lines.append(f"  缺 runtime source: {_format_name_list(sources['missing_runtime'])}")
    if sources["missing_config"]:
        lines.append(f"  缺配置 source: {_format_name_list(sources['missing_config'])}")

    lines.extend(
        [
            "",
            "── Fetch Providers ──",
            (
                f"  {fetch['edition_available']}/{fetch['total']} 个 provider 当前 edition 允许；"
                f"{fetch['runtime_available']} 个 runtime 可加载；"
                f"{fetch['config_available']} 个配置满足；{fetch['available']} 个最终可用"
            ),
        ]
    )
    for bucket, counts in fetch["by_min_edition"].items():
        lines.append(
            f"  min={bucket}: {counts['edition_available']}/{counts['total']} edition 允许"
            f"；{counts['runtime_available']} runtime 可加载；{counts['available']} 最终可用"
        )
    if fetch["upgrade_required"]:
        lines.append(f"  需升级 provider: {_format_name_list(fetch['upgrade_required'])}")
    if fetch["missing_runtime"]:
        lines.append(f"  缺 runtime provider: {_format_name_list(fetch['missing_runtime'])}")
    if fetch["missing_config"]:
        lines.append(f"  缺配置 provider: {_format_name_list(fetch['missing_config'])}")

    if not llm["edition_available"]:
        llm_status = f"需升级（{llm['edition_reason']}）"
    elif not llm["runtime_available"]:
        llm_status = f"缺依赖（{llm['runtime_reason']}）"
    else:
        llm_status = "可用"

    if not plugins["edition_available"]:
        plugin_status = f"需升级（{plugins['edition_reason']}）"
    elif not plugins["runtime_available"]:
        plugin_status = f"缺依赖（{plugins['runtime_reason']}）"
    else:
        plugin_status = "已预装"
    lines.extend(
        [
            "",
            "── Cross-cutting ──",
            f"  WARP 可用模式: {_format_name_list(warp['available_modes'])}",
            f"  WARP 需升级模式: {_format_name_list(warp['upgrade_required'])}",
            f"  LLM: {llm_status}",
            (
                "  Package extras: "
                f"{len(available_extras)}/{len(extra_names)} 可导入；"
                f"已声明: {_format_name_list(extra_names)}"
            ),
            (
                "  Preinstalled plugins: "
                f"{plugin_status}；候选模块: {_format_name_list(plugins['candidate_modules'])}"
            ),
        ]
    )
    if extra_reason:
        lines.append(f"  Package extra 缺失: {extra_reason}")

    return "\n".join(lines)


def _optional_credential_message(meta: Any, configured: bool) -> tuple[str, str]:
    """生成可选凭据源的状态与提示。"""
    field_label = credential_fields_label(meta.credential_fields)
    if not field_label:
        return "ok", "免配置可用"
    if configured:
        return "ok", f"{field_label} 已配置"
    effect = meta.optional_credential_effect or "unknown"
    effect_label = OPTIONAL_CREDENTIAL_EFFECT_LABELS.get(effect, "增强能力")
    message = f"免配置可用；设置 {field_label} 可{effect_label}"
    if effect in _LIMITED_OPTIONAL_EFFECTS:
        return "limited", message
    return "ok", message


def _append_usage_note(message: str, meta: Any) -> str:
    """如果 meta 提供了 usage_note，把它追加到 message 末尾。"""
    note = getattr(meta, "usage_note", None)
    if not note:
        return message
    if note in message:
        return message
    return f"{message}（{note}）"


def _stability_status(meta: Any) -> tuple[str, str] | None:
    """按 stability 维度推断状态/消息；非 deprecated/experimental scraper 返回 None。

    规则：
      - ``stability == "deprecated"`` → ``unavailable``。message 优先取 usage_note，
        回退为 description 中的 "（待修复）" 类提示。
      - ``stability == "experimental"`` 且为爬虫源 → ``warning``。message 优先取
        usage_note，回退为通用"实验性爬虫"提示。

    其他 stability 值（``stable`` / ``beta`` / 非爬虫的 ``experimental``）继续走
    标准 auth_requirement 路径。
    """
    stability = getattr(meta, "stability", "stable")
    note = getattr(meta, "usage_note", None)
    if stability == "deprecated":
        return "unavailable", note or f"{meta.name} 当前接入待修复"
    if stability == "experimental" and getattr(meta, "integration_type", "") == "scraper":
        return "warning", note or "实验性爬虫，可能受反爬或 HTML 变更影响"
    return None


def check_all() -> list[dict]:
    """检查所有数据源的可用性

    遍历所有已注册数据源，检查配置、依赖和服务状态。

    Returns:
        每个数据源一条字典，包含：
        - name: 源名称
        - category: 正式 catalog 分类
        - status: 状态（ok|warning|limited|unavailable|missing_key|disabled）
        - integration_type: 集成类型（open_api|scraper|official_api|self_hosted）
        - required_key: 必需的配置字段名（或 None）
        - key_requirement: 配置 Key 需求级别（self_hosted|none|required|optional）
        - message: 状态说明文本
        - enabled: 是否启用
        - min_edition: 使用该源所需的最低功能档位
        - edition: 当前功能档位
        - edition_available: 当前 edition 是否允许该源
        - edition_reason: edition 不允许时的原因
        - runtime_available / runtime_reason: 当前进程能否加载实现及其可选依赖
        - config_available / config_reason: 当前启用状态与必需凭据是否满足
        - available: edition、runtime、config 与静态状态的有效合取
        - description: 源描述
        - channel: 频道配置摘要（如 proxy、http_backend、base_url）
    """
    cfg = get_config()
    results: list[dict] = []
    catalog = source_catalog()

    # 检测 curl_cffi（TLS 指纹伪装）可用性，影响所有爬虫引擎
    # 爬虫类源需要 curl_cffi 来实现 JA3 TLS 指纹伪装，避免被反爬拦截
    try:
        import curl_cffi  # noqa: F401

        _has_tls_impersonation = True
    except ImportError:
        _has_tls_impersonation = False

    for name, meta in catalog.items():
        adapter = get_adapter(name)
        if adapter is None:  # pragma: no cover - catalog 与 registry 同源，防御漂移
            raise KeyError(f"missing registry adapter for source {name!r}")
        enabled = cfg.is_source_enabled(name, default=adapter.runtime_default_enabled)
        edition = source_policy(adapter, cfg.edition)
        runtime = (
            probe_adapter_runtime(adapter)
            if edition.available
            else RuntimeProbe(False, f"runtime not probed because {edition.reason}")
        )
        field = meta.config_field
        missing_fields = missing_credential_fields(cfg, name, meta)
        has_all_credentials = not missing_fields
        credentials_satisfied = has_required_credentials(cfg, name, meta)
        validation_reason = source_config_validation_reason(cfg, name, meta)
        config_available = enabled and credentials_satisfied and not validation_reason
        if not enabled:
            config_reason = "disabled by source configuration"
        elif validation_reason:
            config_reason = validation_reason
        elif not credentials_satisfied:
            config_reason = (
                f"missing configuration: {credential_fields_label(tuple(missing_fields))}"
                if missing_fields
                else "required configuration is missing"
            )
        else:
            config_reason = ""

        # 状态判定优先级：
        #   1. 频道禁用 → disabled
        #   2. source 配置违反静态约束 → unavailable
        #   3. 当前 edition 不允许 → unavailable（需要升级）
        #   4. 当前 runtime/optional dependency 不可导入 → unavailable
        #   5. stability == "deprecated" → unavailable（接入待修复 / 已下线）
        #   6. stability == "experimental" + scraper → warning（默认调度需谨慎）
        #   7. auth_requirement 标准路径（none / optional / self_hosted / required）
        #   8. scraper 缺 curl_cffi 时把可用状态升级为 warning
        # ``usage_note`` 始终作为消息后缀附加（如 unpaywall 的"仅支持 DOI OA 查找"）。
        if not enabled:
            status = "disabled"
            message = "已通过频道配置禁用"
        elif validation_reason:
            status = "unavailable"
            message = validation_reason
        elif not edition.available:
            status = "unavailable"
            message = edition.reason
        elif not runtime.available:
            status = "unavailable"
            message = runtime.reason
        else:
            stability_override = _stability_status(meta)
            if stability_override is not None:
                status, message = stability_override
            elif meta.auth_requirement == "none":
                status = "ok"
                message = "免配置；未做实时可用性探测"
            elif meta.auth_requirement == "optional":
                status, message = _optional_credential_message(meta, has_all_credentials)
            elif meta.auth_requirement == "self_hosted":
                if not meta.credential_fields:
                    status = "ok"
                    message = "自建实例配置由插件或默认配置提供"
                elif has_all_credentials:
                    status = "ok"
                    message = f"{credential_fields_label(meta.credential_fields)} 已配置"
                else:
                    status = "missing_key"
                    message = f"需要配置自建实例: {credential_fields_label(missing_fields)}"
            else:
                if has_all_credentials:
                    status = "ok"
                    message = f"{credential_fields_label(meta.credential_fields)} 已配置"
                else:
                    status = "missing_key"
                    message = f"需要设置 {credential_fields_label(missing_fields)}"
            message = _append_usage_note(message, meta)

        if (
            enabled
            and status in {"ok", "limited"}
            and meta.integration_type == "scraper"
            and not _has_tls_impersonation
        ):
            if status == "ok":
                status = "warning"
                message = "curl_cffi 未安装，TLS 指纹伪装不可用，爬虫可能被拦截"
            else:
                message = f"{message}；curl_cffi 未安装，爬虫能力可能受限"

        # 频道配置摘要
        sc = cfg.get_source_config(name)
        channel_info: dict[str, str] = {}
        if sc.proxy != "inherit":
            channel_info["proxy"] = sc.proxy
        if sc.http_backend != "auto":
            channel_info["http_backend"] = sc.http_backend
        hides_gateway_values = any(
            is_llm_search_gateway_requirement(item) for item in adapter.resolved_credential_fields
        )
        if sc.base_url and not hides_gateway_values:
            channel_info["base_url"] = sc.base_url
        if sc.timeout is not None:
            channel_info["timeout"] = str(sc.timeout)

        results.append(
            {
                "name": name,
                "category": meta.category,
                "status": status,
                "integration_type": meta.integration_type,
                "required_key": field,
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
                "message": message,
                "enabled": enabled,
                "min_edition": edition.min_edition,
                "edition": cfg.edition,
                "edition_available": edition.available,
                "edition_reason": edition.reason,
                "runtime_available": runtime.available,
                "runtime_reason": runtime.reason,
                "credentials_satisfied": credentials_satisfied,
                "missing_credential_fields": list(missing_fields),
                "config_valid": not validation_reason,
                "config_available": config_available,
                "config_reason": config_reason,
                "available": (
                    edition.available
                    and runtime.available
                    and config_available
                    and is_available_status(status)
                ),
                "description": meta.description,
                "channel": channel_info if channel_info else None,
            }
        )

    return results


def _source_names_filter(sources: list[str] | str | None) -> set[str] | None:
    if sources is None:
        return None
    if isinstance(sources, str):
        items = [sources]
    else:
        items = list(sources)
    return {item.strip() for item in items if item.strip()}


def _live_probe_skipped(message: str) -> dict[str, Any]:
    return {"status": "skipped", "message": message, "elapsed_ms": 0}


async def _live_probe_source(
    item: dict,
    *,
    query: str,
    timeout: float,
) -> dict[str, Any]:
    """Run a bounded live search probe for one statically available source."""

    name = str(item["name"])
    if not item.get("enabled"):
        return _live_probe_skipped("source is disabled")
    if not item.get("edition_available"):
        return _live_probe_skipped(str(item.get("edition_reason") or "edition unavailable"))
    if not item.get("available"):
        return _live_probe_skipped(f"static status is {item.get('status')}")

    adapter = get_adapter(name)
    if adapter is None:
        return _live_probe_skipped("registry adapter is missing")
    if "search" not in adapter.capabilities:
        return _live_probe_skipped("source does not expose search capability")

    from souwen.search import _run_via_adapter

    started = time.monotonic()
    try:
        response = await asyncio.wait_for(
            _run_via_adapter(adapter, "search", query=query, limit=1),
            timeout=timeout,
        )
    except ConfigError as exc:
        return {
            "status": "skipped",
            "message": f"missing config: {exc}",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    except RateLimitError as exc:
        return {
            "status": "failed",
            "message": f"rate limited: {exc}",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    except asyncio.TimeoutError:
        return {
            "status": "failed",
            "message": f"timed out after {timeout:g}s",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001 - live doctor reports failures, not exceptions.
        return {
            "status": "failed",
            "message": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    error = getattr(response, "error", None)
    if error:
        return {
            "status": "failed",
            "message": str(error),
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    results = getattr(response, "results", None)
    result_count = len(results) if isinstance(results, list) else None
    detail = f"live search returned {result_count} result(s)" if result_count is not None else "ok"
    return {
        "status": "ok",
        "message": detail,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


async def check_all_live(
    *,
    sources: list[str] | str | None = None,
    query: str = LIVE_PROBE_QUERY,
    timeout: float = LIVE_PROBE_TIMEOUT_SECONDS,
) -> list[dict]:
    """Run explicit live probes and attach ``live_probe`` to the matching sources.

    This is intentionally opt-in. ``check_all()`` remains static and deterministic;
    this function may touch external services and should be used only for CLI/API
    paths where the user explicitly asks for live checks.
    """

    results = check_all()
    selected = _source_names_filter(sources)
    targets = [
        item for item in results if selected is None or str(item.get("name") or "") in selected
    ]
    if not targets:
        return results

    timeout = max(0.5, float(timeout))
    probes = await asyncio.gather(
        *[_live_probe_source(item, query=query, timeout=timeout) for item in targets]
    )
    by_name = {str(item["name"]): item for item in results}
    for item, probe in zip(targets, probes, strict=True):
        by_name[str(item["name"])]["live_probe"] = probe
    return results


def format_report(results: list[dict]) -> str:
    """将 check_all() 结果格式化为可读报告

    按集成类型（integration_type）分组展示，每组显示可用数量和详细列表。

    Args:
        results: check_all() 的返回值

    Returns:
        格式化的报告字符串（Markdown 风格，包含 Emoji 和缩进）

    输出示例：
        🩺 SouWen Doctor — 数据源健康检查
           OK/总数 个数据源可用

        ── 公开接口 — 免配置 / 官方开放 API  (OK数/总数) ──
          ⚠️ openalex           [paper]    免配置可用；设置 openalex_api_key 可提升配额...
          ...
    """
    counts = summarize_statuses(results)
    total = int(counts["total"])
    available_count = int(counts["available"])
    edition = (
        str(results[0].get("edition") or get_config().edition) if results else get_config().edition
    )
    lines: list[str] = [
        f"🩺 SouWen Doctor — 数据源健康检查 (edition={edition})",
        f"   {available_count}/{total} 个数据源可用\n",
    ]
    live_summary = summarize_live_probes(results)
    if live_summary["total"]:
        lines.append(
            "   live probe: "
            f"{live_summary['ok']}/{live_summary['total']} ok, "
            f"{live_summary['failed']} failed, {live_summary['skipped']} skipped\n"
        )

    # 按集成类型分组
    by_type: dict[str, list[dict]] = {t: [] for t in _INTEGRATION_TYPE_ORDER}
    for r in results:
        by_type.setdefault(r["integration_type"], []).append(r)

    for itype in _INTEGRATION_TYPE_ORDER:
        items = by_type[itype]
        if not items:
            continue
        type_ok = sum(1 for r in items if is_available_status(r.get("status")))
        label = INTEGRATION_TYPE_LABELS.get(itype, itype)
        lines.append(f"── {label}  ({type_ok}/{len(items)}) ──")
        for r in items:
            icon = _STATUS_ICONS.get(r["status"], "⬜")
            cat_tag = f"[{r['category']}]"
            kr = r.get("key_requirement", "")
            kr_tag = AUTH_REQUIREMENT_LABELS.get(kr, "")
            live_probe = r.get("live_probe")
            live_text = ""
            if isinstance(live_probe, dict):
                live_status = str(live_probe.get("status") or "unknown")
                live_message = str(live_probe.get("message") or "")
                live_text = f"；live={live_status}: {live_message}"
            lines.append(
                f"  {icon} {r['name']:20s} {cat_tag:10s} {kr_tag:6s}  {r['message']}{live_text}"
            )
        lines.append("")

    return "\n".join(lines)
