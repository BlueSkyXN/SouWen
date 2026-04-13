"""SouWen 数据源健康检查

检测所有数据源的可用性，按配置 Tier 分组显示。
"""

from __future__ import annotations

from souwen.config import get_config

# (config_field_or_None, tier)
# Tier 0 = 零配置, Tier 1 = 免费 Key / 自建 URL, Tier 2 = 付费 Key
_SOURCE_CONFIG: dict[str, tuple[str | None, int]] = {
    # paper
    "openalex": ("openalex_email", 0),
    "semantic_scholar": ("semantic_scholar_api_key", 1),
    "crossref": (None, 0),
    "arxiv": (None, 0),
    "dblp": (None, 0),
    "core": ("core_api_key", 1),
    "pubmed": (None, 0),
    "unpaywall": ("unpaywall_email", 1),
    # patent
    "patentsview": (None, 0),
    "pqai": (None, 0),
    "epo_ops": ("epo_consumer_key", 2),
    "uspto_odp": ("uspto_api_key", 2),
    "the_lens": ("lens_api_token", 2),
    "cnipa": ("cnipa_client_id", 2),
    "patsnap": ("patsnap_api_key", 2),
    "google_patents": (None, 0),
    # web - scrapers (tier 0)
    "duckduckgo": (None, 0),
    "yahoo": (None, 0),
    "brave": (None, 0),
    "google": (None, 0),
    "bing": (None, 0),
    "startpage": (None, 0),
    "baidu": (None, 0),
    "mojeek": (None, 0),
    "yandex": (None, 0),
    # web - self-hosted (tier 1)
    "searxng": ("searxng_url", 1),
    "whoogle": ("whoogle_url", 1),
    "websurfx": ("websurfx_url", 1),
    # web - paid API (tier 2)
    "tavily": ("tavily_api_key", 2),
    "exa": ("exa_api_key", 2),
    "serper": ("serper_api_key", 2),
    "brave_api": ("brave_api_key", 2),
    "serpapi": ("serpapi_api_key", 2),
    "firecrawl": ("firecrawl_api_key", 2),
    "perplexity": ("perplexity_api_key", 2),
    "linkup": ("linkup_api_key", 2),
    "scrapingdog": ("scrapingdog_api_key", 2),
}

# 数据源 → 类别
_SOURCE_CATEGORY: dict[str, str] = {}
_PAPER_NAMES = {
    "openalex",
    "semantic_scholar",
    "crossref",
    "arxiv",
    "dblp",
    "core",
    "pubmed",
    "unpaywall",
}
_PATENT_NAMES = {
    "patentsview",
    "pqai",
    "epo_ops",
    "uspto_odp",
    "the_lens",
    "cnipa",
    "patsnap",
    "google_patents",
}
for _n in _SOURCE_CONFIG:
    if _n in _PAPER_NAMES:
        _SOURCE_CATEGORY[_n] = "paper"
    elif _n in _PATENT_NAMES:
        _SOURCE_CATEGORY[_n] = "patent"
    else:
        _SOURCE_CATEGORY[_n] = "web"

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
}


def check_all() -> list[dict]:
    """检查所有数据源的可用性。

    Returns:
        每个数据源一条字典: name, category, status, tier, required_key, message
    """
    cfg = get_config()
    results: list[dict] = []

    for name, (field, tier) in _SOURCE_CONFIG.items():
        if name == "openalex":
            value = getattr(cfg, "openalex_email", None)
            if value:
                status = "ok"
                message = "openalex_email 已配置"
            else:
                status = "ok"
                message = "可免配置使用；设置 openalex_email 可帮助礼貌访问"
        elif name == "semantic_scholar":
            value = getattr(cfg, "semantic_scholar_api_key", None)
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
            value = getattr(cfg, "unpaywall_email", None)
            if value:
                status = "ok"
                message = "unpaywall_email 已配置（仅 DOI OA 查找）"
            else:
                status = "missing_key"
                message = "需要设置 unpaywall_email（仅支持 DOI OA 查找）"
        elif field is None:
            status = "ok"
            message = "免配置；未做实时可用性探测"
        else:
            value = getattr(cfg, field, None)
            if value:
                status = "ok"
                message = f"{field} 已配置"
            else:
                status = "missing_key"
                message = f"需要设置 {field}"

        results.append(
            {
                "name": name,
                "category": _SOURCE_CATEGORY[name],
                "status": status,
                "tier": tier,
                "required_key": field,
                "message": message,
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
