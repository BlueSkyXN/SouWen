"""registry/views.py — 面向消费者的查询视图

所有对外查询都走这个模块。内部表 _REGISTRY 由 sources.py 填充。

使用者：
  - souwen.search（门面）
  - souwen.web.search（门面）
  - souwen.source_registry（SourceMeta 视图）
  - souwen.models.ALL_SOURCES（派生）
  - server/routes 的 /sources 端点
  - CLI 的 sources 子命令
  - docs 自动生成脚本
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from souwen.registry.adapter import FETCH_DOMAIN, SourceAdapter

# ── 内部注册表（由 sources.py 填充）─────────────────────────
_REGISTRY: dict[str, SourceAdapter] = {}


def _reg(adapter: SourceAdapter) -> None:
    """注册一个 adapter。同名重复注册抛异常（避免 sources.py 里的漂移）。"""
    if adapter.name in _REGISTRY:
        raise ValueError(
            f"重复注册数据源: {adapter.name!r}（已存在 {_REGISTRY[adapter.name]!r}）"
        )
    _REGISTRY[adapter.name] = adapter


# ── 查询 API ────────────────────────────────────────────────

def get(name: str) -> SourceAdapter | None:
    """按名字取单个 adapter，不存在返回 None。"""
    return _REGISTRY.get(name)


def all_adapters() -> dict[str, SourceAdapter]:
    """返回所有 adapter 的拷贝 dict。"""
    return dict(_REGISTRY)


def by_domain(domain: str) -> list[SourceAdapter]:
    """某 domain 下的所有 adapter（包含以 extra_domains 方式加入的）。

    例：`by_domain("fetch")` 会包含 wayback / tavily / firecrawl / exa 等。
    """
    return [a for a in _REGISTRY.values() if domain in a.domains]


def by_capability(capability: str) -> list[SourceAdapter]:
    """支持某个 capability 的所有 adapter。"""
    return [a for a in _REGISTRY.values() if capability in a.capabilities]


def by_domain_and_capability(domain: str, capability: str) -> list[SourceAdapter]:
    """同时满足 domain + capability 的 adapter（门面主要的派发路径）。"""
    return [
        a
        for a in _REGISTRY.values()
        if domain in a.domains and capability in a.capabilities
    ]


def defaults_for(domain: str, capability: str = "search") -> list[str]:
    """(domain, capability) 未显式指定 sources 时的默认源列表。

    来自 adapter.default_for 字段（D9）。
    """
    key = f"{domain}:{capability}"
    return [a.name for a in _REGISTRY.values() if key in a.default_for]


def all_domains() -> list[str]:
    """注册表里出现过的所有 domain（含 fetch）的去重列表。

    前端的 /sources.domains 字段就从这里来（D13）。
    """
    seen: set[str] = set()
    for a in _REGISTRY.values():
        seen.update(a.domains)
    # 保持一个相对稳定的显示顺序：官方 10 个 domain + fetch 放最后
    order = [
        "paper", "patent", "web", "social", "video",
        "knowledge", "developer", "cn_tech", "office", "archive",
        FETCH_DOMAIN,
    ]
    sorted_list: list[str] = [d for d in order if d in seen]
    # 容纳未来可能新增的 domain，按字母序附在末尾
    extras = sorted(seen - set(order))
    return sorted_list + extras


def all_capabilities() -> list[str]:
    """注册表里出现过的所有 capability（含 'xxx:yyy' 命名空间）。"""
    seen: set[str] = set()
    for a in _REGISTRY.values():
        seen.update(a.capabilities)
    return sorted(seen)


def fetch_providers() -> list[SourceAdapter]:
    """所有能做 fetch 的源：domain=fetch 或 extra_domains 含 fetch。"""
    return by_domain(FETCH_DOMAIN)


def high_risk_sources() -> list[str]:
    """tags 包含 'high_risk' 的源名列表（D10）。"""
    return [a.name for a in _REGISTRY.values() if "high_risk" in a.tags]


def enum_values() -> list[str]:
    """所有 adapter 名的排序列表，供 SourceType 枚举派生（D4）。"""
    return sorted(_REGISTRY.keys())


# ── ALL_SOURCES 兼容视图 ────────────────────────────────────

#: domain → ALL_SOURCES 分类的映射（ALL_SOURCES 包含的 9 个分类）。
#: 注意：`general` 混了 engines + self_hosted + 部分 SERP API，
#:      `professional` 是另一批 SERP/AI 类 API。
_DOMAIN_TO_CATEGORY: dict[str, str] = {
    "paper": "paper",
    "patent": "patent",
    "social": "social",
    "video": "video",
    "knowledge": "wiki",     # 历史命名 "wiki"
    "developer": "developer",
    "cn_tech": "cn_tech",
    "office": "office",
    "archive": "fetch",      # wayback 归在 fetch
    FETCH_DOMAIN: "fetch",
}


def _v0_category_for(adapter: SourceAdapter) -> str | None:
    """把 adapter 映射到 ALL_SOURCES key。web 分两类：general / professional。

    对 domain=web 的源：
      - integration ∈ {scraper, self_hosted, 部分 official_api 型 SERP 引擎} → general
      - integration=official_api 且以 AI/搜索聚合为主 → professional

    判定走 tags（"v0_category:general" / "v0_category:professional"）显式标记，
    这样不会在维度推断上纠结。
    """
    if "v0_category:general" in adapter.tags:
        return "general"
    if "v0_category:professional" in adapter.tags:
        return "professional"
    return _DOMAIN_TO_CATEGORY.get(adapter.domain)


def as_all_sources_dict() -> dict[str, list[tuple[str, bool, str]]]:
    """派生 `ALL_SOURCES` 字典结构（用于 `models.ALL_SOURCES`）。

    返回格式：`{category: [(name, needs_config, description), ...]}`
    category 仅包含 adapter 实际覆盖到的（空分类不会出现）。

    fetch 特殊处理：主 domain=fetch 以及 extra_domains 含 fetch 的 adapter
    都会出现在 fetch 列表里。

    排除规则：adapter.tags 含 `v0_all_sources:exclude` 的源**不出现**在返回值中。
    用于历史上未列入 ALL_SOURCES 的实验性/"待修复"源（unpaywall / patentsview / pqai），
    这些源仍然保留在注册表里供未来启用。
    """
    result: dict[str, list[tuple[str, bool, str]]] = {}
    for adapter in _REGISTRY.values():
        if "v0_all_sources:exclude" in adapter.tags:
            continue
        category = _v0_category_for(adapter)
        if category is not None:
            result.setdefault(category, []).append(
                (adapter.name, adapter.resolved_needs_config, adapter.description)
            )
        # 跨域 fetch
        if FETCH_DOMAIN in adapter.extra_domains and adapter.domain != FETCH_DOMAIN:
            fetch_list = result.setdefault("fetch", [])
            if not any(t[0] == adapter.name for t in fetch_list):
                fetch_list.append(
                    (adapter.name, adapter.resolved_needs_config, adapter.description)
                )
    # 稳定的 category 顺序
    order = [
        "paper", "patent", "general", "professional",
        "social", "office", "developer", "wiki",
        "cn_tech", "video", "fetch",
    ]
    return {k: result[k] for k in order if k in result}


# ── 便于测试 / 脚本使用 ────────────────────────────────────

def _reset_registry() -> None:
    """仅供测试：清空注册表。生产代码不要调用。"""
    _REGISTRY.clear()


def _load_default_sources() -> None:
    """显式触发 sources.py 的 import（保证注册表已填充）。

    一般不需要手动调用：任何视图函数第一次被调用时，模块链已经
    把 sources.py 拉进来（因为 sources.py 自身 import 了 views._reg）。
    但单元测试里把注册表清空后要手动重新加载。
    """
    from souwen.registry import sources  # noqa: F401


def _iter_default_for_triples() -> list[tuple[str, str, str]]:
    """内部用：展开 default_for，返回 (name, domain, capability) 三元组列表。"""
    triples: list[tuple[str, str, str]] = []
    for a in _REGISTRY.values():
        for key in a.default_for:
            dom, _, cap = key.partition(":")
            triples.append((a.name, dom, cap))
    return triples


__all__ = [
    "get",
    "all_adapters",
    "by_domain",
    "by_capability",
    "by_domain_and_capability",
    "defaults_for",
    "all_domains",
    "all_capabilities",
    "fetch_providers",
    "high_risk_sources",
    "enum_values",
    "as_all_sources_dict",
]

# 注：保留下列符号供 sources.py 内部使用，但不公开
_public_internal: tuple[Callable[..., Any], ...] = (_reg,)  # type: ignore[assignment]
