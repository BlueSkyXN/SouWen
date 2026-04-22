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
    - souwen.source_registry: 获取所有注册源、元数据、集成类型标签
"""

from __future__ import annotations

from souwen.config import get_config
from souwen.source_registry import INTEGRATION_TYPE_LABELS, get_all_sources

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


def check_all() -> list[dict]:
    """检查所有数据源的可用性

    遍历所有已注册数据源，检查配置、依赖和服务状态。

    Returns:
        每个数据源一条字典，包含：
        - name: 源名称
        - category: 分类（paper|patent|general|professional|social|developer|wiki|video|fetch）
        - status: 状态（ok|warning|limited|unavailable|missing_key|disabled）
        - integration_type: 集成类型（open_api|scraper|official_api|self_hosted）
        - required_key: 必需的配置字段名（或 None）
        - key_requirement: 配置 Key 需求级别（self_hosted|none|required|optional）
        - message: 状态说明文本
        - enabled: 是否启用
        - description: 源描述
        - channel: 频道配置摘要（如 proxy、http_backend、base_url）
    """
    cfg = get_config()
    results: list[dict] = []
    all_sources = get_all_sources()

    # 检测 curl_cffi（TLS 指纹伪装）可用性，影响所有爬虫引擎
    # 爬虫类源需要 curl_cffi 来实现 JA3 TLS 指纹伪装，避免被反爬拦截
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
            message = "公开搜索端点已变更，当前接入待修复"
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

        # 派生 key_requirement：self_hosted 类源单独标识；其余按 config_field/needs_config 判定
        if meta.integration_type == "self_hosted":
            key_requirement = "self_hosted"
        elif field is None:
            key_requirement = "none"
        elif meta.needs_config:
            key_requirement = "required"
        else:
            key_requirement = "optional"

        results.append(
            {
                "name": name,
                "category": meta.category,
                "status": status,
                "integration_type": meta.integration_type,
                "required_key": field,
                "key_requirement": key_requirement,
                "message": message,
                "enabled": enabled,
                "description": meta.description,
                "channel": channel_info if channel_info else None,
            }
        )

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
          ✅ openalex           [paper]    可免配置使用；设置 openalex_email...
          ...
    """
    total = len(results)
    ok_count = sum(1 for r in results if r["status"] == "ok")
    lines: list[str] = [
        "🩺 SouWen Doctor — 数据源健康检查",
        f"   {ok_count}/{total} 个数据源可用\n",
    ]

    # 按集成类型分组
    by_type: dict[str, list[dict]] = {t: [] for t in _INTEGRATION_TYPE_ORDER}
    for r in results:
        by_type.setdefault(r["integration_type"], []).append(r)

    for itype in _INTEGRATION_TYPE_ORDER:
        items = by_type[itype]
        if not items:
            continue
        type_ok = sum(1 for r in items if r["status"] == "ok")
        label = INTEGRATION_TYPE_LABELS.get(itype, itype)
        lines.append(f"── {label}  ({type_ok}/{len(items)}) ──")
        for r in items:
            icon = _STATUS_ICONS.get(r["status"], "⬜")
            cat_tag = f"[{r['category']}]"
            kr = r.get("key_requirement", "")
            kr_tag = {
                "none": "免配置",
                "optional": "可选Key",
                "required": "需Key",
                "self_hosted": "需自建",
            }.get(kr, "")
            lines.append(f"  {icon} {r['name']:20s} {cat_tag:10s} {kr_tag:6s}  {r['message']}")
        lines.append("")

    return "\n".join(lines)
