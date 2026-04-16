"""SouWen 数据源健康检查

检测所有数据源的可用性，按配置 Tier 分组显示。
"""

from __future__ import annotations

from souwen.config import get_config
from souwen.source_registry import get_all_sources

_TIER_LABELS = {
    0: "Tier 0 — 免配置 / 公开入口",
    1: "Tier 1 — 免费 Key / 自建服务",
    2: "Tier 2 — 付费 Key",
}

_STATUS_ICONS = {
    "ok": "✅",
    "warning": "⚠️",
    "limited": "⚠️",
    "unavailable": "❌",
    "missing_key": "⬜",
    "disabled": "🚫",
}


def check_all() -> list[dict]:
    """检查所有数据源的可用性。

    Returns:
        每个数据源一条字典: name, category, status, tier, required_key, message, enabled
    """
    cfg = get_config()
    results: list[dict] = []
    all_sources = get_all_sources()

    # 检测 curl_cffi（TLS 指纹伪装）可用性，影响所有爬虫引擎
    try:
        import curl_cffi  # noqa: F401

        _has_tls_impersonation = True
    except ImportError:
        _has_tls_impersonation = False

    for name, meta in all_sources.items():
        enabled = cfg.is_source_enabled(name)
        field = meta.config_field

        if not enabled:
            status = "disabled"
            message = "已通过频道配置禁用"
        elif name == "openalex":
            value = cfg.resolve_api_key("openalex", "openalex_email")
            if value:
                status = "ok"
                message = "openalex_email 已配置"
            else:
                status = "ok"
                message = "可免配置使用；设置 openalex_email 可帮助礼貌访问"
        elif name == "semantic_scholar":
            value = cfg.resolve_api_key("semantic_scholar", "semantic_scholar_api_key")
            if value:
                status = "ok"
                message = "semantic_scholar_api_key 已配置"
            else:
                status = "limited"
                message = "免 Key 模式易限流，建议设置 semantic_scholar_api_key"
        elif name == "patentsview":
            status = "unavailable"
            message = "公开搜索端点已迁移，当前接入待修复"
        elif name == "pqai":
            status = "unavailable"
            message = "匿名 API 当前返回 401，暂不建议默认使用"
        elif name == "google_patents":
            status = "warning"
            message = "实验性爬虫，易受反爬影响"
        elif name == "unpaywall":
            value = cfg.resolve_api_key("unpaywall", "unpaywall_email")
            if value:
                status = "ok"
                message = "unpaywall_email 已配置（仅 DOI OA 查找）"
            else:
                status = "missing_key"
                message = "需要设置 unpaywall_email（仅支持 DOI OA 查找）"
        elif field is None:
            # 爬虫引擎需要 curl_cffi 才能正常工作
            if meta.is_scraper and not _has_tls_impersonation:
                status = "warning"
                message = "curl_cffi 未安装，TLS 指纹伪装不可用，爬虫可能被拦截"
            else:
                status = "ok"
                message = "免配置；未做实时可用性探测"
        else:
            value = cfg.resolve_api_key(name, field)
            if value:
                status = "ok"
                message = f"{field} 已配置"
            else:
                status = "missing_key"
                message = f"需要设置 {field}"

        # 频道配置摘要
        sc = cfg.get_source_config(name)
        channel_info: dict[str, str] = {}
        if sc.proxy != "inherit":
            channel_info["proxy"] = sc.proxy
        if sc.http_backend != "auto":
            channel_info["http_backend"] = sc.http_backend
        if sc.base_url:
            channel_info["base_url"] = sc.base_url

        results.append(
            {
                "name": name,
                "category": meta.category,
                "status": status,
                "tier": meta.tier,
                "required_key": field,
                "message": message,
                "enabled": enabled,
                "description": meta.description,
                "channel": channel_info if channel_info else None,
            }
        )

    return results


def format_report(results: list[dict]) -> str:
    """将 check_all() 结果格式化为可读报告。"""
    total = len(results)
    ok_count = sum(1 for r in results if r["status"] == "ok")
    lines: list[str] = [
        "🩺 SouWen Doctor — 数据源健康检查",
        f"   {ok_count}/{total} 个数据源可用\n",
    ]

    by_tier: dict[int, list[dict]] = {0: [], 1: [], 2: []}
    for r in results:
        by_tier[r["tier"]].append(r)

    for tier in (0, 1, 2):
        items = by_tier[tier]
        tier_ok = sum(1 for r in items if r["status"] == "ok")
        lines.append(f"── {_TIER_LABELS[tier]}  ({tier_ok}/{len(items)}) ──")
        for r in items:
            icon = _STATUS_ICONS.get(r["status"], "⬜")
            cat_tag = f"[{r['category']}]"
            lines.append(f"  {icon} {r['name']:20s} {cat_tag:10s} {r['message']}")
        lines.append("")

    return "\n".join(lines)
