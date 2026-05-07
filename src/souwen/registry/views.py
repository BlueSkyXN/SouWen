"""registry/views.py — 面向消费者的查询视图

所有对外查询都走这个模块。内部表 _REGISTRY 由 sources package 填充。

使用者：
  - souwen.search（门面）
  - souwen.web.search（门面）
  - souwen.registry.meta（SourceMeta 视图）
  - server/routes 的 /sources 端点
  - CLI 的 sources 子命令
  - docs 自动生成脚本
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from souwen.registry.adapter import FETCH_DOMAIN, SourceAdapter

logger = logging.getLogger("souwen.registry")

# ── 内部注册表（由 sources package 填充）─────────────────────────
_REGISTRY: dict[str, SourceAdapter] = {}

#: 通过外部插件加载的源名集合（用于审计/查询）
_EXTERNAL_PLUGINS: set[str] = set()


def _invalidate_source_meta_cache() -> None:
    """外部插件改动 registry 后，同步刷新 SourceMeta 兼容视图。"""
    try:
        from souwen.registry.meta import invalidate_source_meta_cache
    except ImportError:  # pragma: no cover - 仅防御极早期 import 环
        return
    invalidate_source_meta_cache()


def _reg(adapter: SourceAdapter) -> None:
    """注册一个 adapter。同名重复注册抛异常（避免 sources package 里的漂移）。"""
    if adapter.name in _REGISTRY:
        raise ValueError(f"重复注册数据源: {adapter.name!r}（已存在 {_REGISTRY[adapter.name]!r}）")
    _REGISTRY[adapter.name] = adapter


def _reg_external(adapter: SourceAdapter) -> bool:
    """注册一个外部插件 adapter。

    与 `_reg` 不同：发生重名冲突时 **不抛异常**，仅记录警告并跳过，
    保证宿主程序不会因为第三方插件冲突而崩溃。

    Returns:
        True 表示注册成功；False 表示与已有源冲突或已注册，已跳过。
    """
    if adapter.name in _REGISTRY:
        if adapter.name in _EXTERNAL_PLUGINS:
            # 已由之前的 discover/load 调用注册过，幂等跳过
            return False
        logger.warning(
            "插件源 %r 与已有数据源同名，已跳过（请重命名插件以避免冲突）",
            adapter.name,
        )
        return False
    _REGISTRY[adapter.name] = adapter
    _EXTERNAL_PLUGINS.add(adapter.name)
    _invalidate_source_meta_cache()
    return True


def _unreg_external(name: str) -> bool:
    """运行时注销外部插件 adapter（仅限外部插件，不影响内置源）。

    Returns:
        True 表示成功移除；False 表示不存在或非外部插件。
    """
    if name not in _EXTERNAL_PLUGINS:
        return False
    _EXTERNAL_PLUGINS.discard(name)
    _REGISTRY.pop(name, None)
    _invalidate_source_meta_cache()
    logger.info("已注销外部插件源 %r", name)
    return True


def external_plugins() -> list[str]:
    """返回通过外部插件加载的源名（按字母序）。"""
    return sorted(_EXTERNAL_PLUGINS)


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
    return [a for a in _REGISTRY.values() if domain in a.domains and capability in a.capabilities]


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
        "paper",
        "patent",
        "web",
        "social",
        "video",
        "knowledge",
        "developer",
        "cn_tech",
        "office",
        "archive",
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
    """所有 adapter 名的排序列表，供 source id 派生（D4）。"""
    return sorted(_REGISTRY.keys())


# ── 便于测试 / 脚本使用 ────────────────────────────────────


def _reset_registry() -> None:
    """仅供测试：清空注册表。生产代码不要调用。"""
    _REGISTRY.clear()
    _EXTERNAL_PLUGINS.clear()
    _invalidate_source_meta_cache()


def _load_default_sources() -> None:
    """显式触发 sources package 的 import（保证注册表已填充）。

    一般不需要手动调用：任何视图函数第一次被调用时，模块链已经
    把 sources package 拉进来（因为 sources package 自身 import 了 views._reg）。
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
    "external_plugins",
]

# 注：保留下列符号供 sources package 内部使用，但不公开
_public_internal: tuple[Callable[..., Any], ...] = (_reg, _reg_external, _unreg_external)  # type: ignore[assignment]
