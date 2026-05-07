"""正式 source catalog 投影层。

本模块从底层 ``SourceAdapter`` registry 派生面向展示、治理和后续 API
contract 的 catalog 视图。新代码需要目录语义时应从这里读取。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from souwen.registry import views as _views
from souwen.registry.adapter import (
    FETCH_DOMAIN,
    SOURCE_CATEGORIES,
    SourceAdapter,
)


@dataclass(frozen=True, slots=True)
class SourceCategory:
    """Source catalog 的展示/治理分类。"""

    key: str
    label: str
    domain: str | None
    order: int
    description: str = ""


@dataclass(frozen=True, slots=True)
class SourceCatalogEntry:
    """从 ``SourceAdapter`` 派生出的稳定 catalog 条目。"""

    name: str
    domain: str
    category: str
    capabilities: tuple[str, ...]
    description: str
    integration_type: str
    config_field: str | None
    needs_config: bool
    auth_requirement: str
    credential_fields: tuple[str, ...]
    optional_credential_effect: str | None
    risk_level: str
    risk_reasons: tuple[str, ...]
    stability: str
    distribution: str
    package_extra: str | None
    default_enabled: bool
    default_for: tuple[str, ...]
    visibility: str
    available_by_default: bool
    usage_note: str | None


_SOURCE_CATEGORIES: tuple[SourceCategory, ...] = (
    SourceCategory(
        key="paper",
        label="学术论文",
        domain="paper",
        order=10,
        description="论文、预印本、开放学术索引和文献库。",
    ),
    SourceCategory(
        key="patent",
        label="专利",
        domain="patent",
        order=20,
        description="专利检索、专利详情和专利数据库。",
    ),
    SourceCategory(
        key="web_general",
        label="通用网页搜索",
        domain="web",
        order=30,
        description="通用搜索引擎、SERP 爬虫、自托管元搜索和传统 SERP API。",
    ),
    SourceCategory(
        key="web_professional",
        label="专业网页搜索",
        domain="web",
        order=40,
        description="AI 搜索、语义搜索和商业聚合搜索 API。",
    ),
    SourceCategory(
        key="social",
        label="社交平台",
        domain="social",
        order=50,
        description="社区、社媒和用户生成内容平台。",
    ),
    SourceCategory(
        key="office",
        label="企业/办公",
        domain="office",
        order=60,
        description="企业协同、办公平台和内部知识入口。",
    ),
    SourceCategory(
        key="developer",
        label="开发者社区",
        domain="developer",
        order=70,
        description="代码托管、技术问答和开发者内容平台。",
    ),
    SourceCategory(
        key="knowledge",
        label="百科/知识库",
        domain="knowledge",
        order=80,
        description="百科、知识库和结构化知识检索。",
    ),
    SourceCategory(
        key="cn_tech",
        label="中文技术社区",
        domain="cn_tech",
        order=90,
        description="中文技术社区、产品社区和本土开发者内容平台。",
    ),
    SourceCategory(
        key="video",
        label="视频平台",
        domain="video",
        order=100,
        description="视频搜索、热门视频和字幕类能力。",
    ),
    SourceCategory(
        key="archive",
        label="档案/历史",
        domain="archive",
        order=110,
        description="网页归档查询、快照保存和历史版本检索。",
    ),
    SourceCategory(
        key="fetch",
        label="内容抓取",
        domain=FETCH_DOMAIN,
        order=120,
        description="横切内容抓取 provider 和正文抽取能力。",
    ),
)

_SOURCE_CATEGORY_ORDER: dict[str, int] = {
    category.key: category.order for category in _SOURCE_CATEGORIES
}
_DOMAIN_TO_CATALOG_CATEGORY: dict[str, str] = {
    "paper": "paper",
    "patent": "patent",
    "social": "social",
    "office": "office",
    "developer": "developer",
    "knowledge": "knowledge",
    "cn_tech": "cn_tech",
    "video": "video",
    "archive": "archive",
    FETCH_DOMAIN: "fetch",
}


def _catalog_category_for(adapter: SourceAdapter) -> str:
    """把 adapter 投影到正式 catalog category。"""

    if adapter.category is not None:
        return adapter.category
    if "category:general" in adapter.tags:
        return "web_general"
    if "category:professional" in adapter.tags:
        return "web_professional"
    if adapter.domain == "web":
        return "web_general"
    return _DOMAIN_TO_CATALOG_CATEGORY[adapter.domain]


def _is_available_by_default(adapter: SourceAdapter, visibility: str) -> bool:
    """判断一个源在零配置默认体验里是否适合直接可用。"""

    if visibility != "public":
        return False
    if not adapter.default_enabled:
        return False
    if adapter.resolved_auth_requirement not in {"none", "optional"}:
        return False
    if adapter.resolved_risk_level == "high":
        return False
    return adapter.resolved_stability not in {"experimental", "deprecated"}


def _entry_from_adapter(adapter: SourceAdapter, *, external: bool = False) -> SourceCatalogEntry:
    category = _catalog_category_for(adapter)
    visibility = adapter.catalog_visibility
    distribution = "plugin" if external else adapter.resolved_distribution
    return SourceCatalogEntry(
        name=adapter.name,
        domain=adapter.domain,
        category=category,
        capabilities=tuple(sorted(adapter.capabilities)),
        description=adapter.description,
        integration_type=adapter.integration,
        config_field=adapter.config_field,
        needs_config=adapter.resolved_needs_config,
        auth_requirement=adapter.resolved_auth_requirement,
        credential_fields=adapter.resolved_credential_fields,
        optional_credential_effect=adapter.optional_credential_effect,
        risk_level=adapter.resolved_risk_level,
        risk_reasons=tuple(sorted(adapter.resolved_risk_reasons)),
        stability=adapter.resolved_stability,
        distribution=distribution,
        package_extra=adapter.resolved_package_extra,
        default_enabled=adapter.default_enabled,
        default_for=tuple(sorted(adapter.default_for)),
        visibility=visibility,
        available_by_default=_is_available_by_default(adapter, visibility),
        usage_note=adapter.usage_note,
    )


def source_categories() -> tuple[SourceCategory, ...]:
    """返回按展示顺序排列的 catalog categories。"""

    return _SOURCE_CATEGORIES


def source_catalog() -> dict[str, SourceCatalogEntry]:
    """返回所有注册源的正式 catalog 投影，包含 hidden/internal 条目。"""

    external_names = set(_views.external_plugins())
    entries = [
        _entry_from_adapter(adapter, external=adapter.name in external_names)
        for adapter in _views.all_adapters().values()
    ]
    entries.sort(key=lambda item: (_SOURCE_CATEGORY_ORDER[item.category], item.name))
    return {entry.name: entry for entry in entries}


def public_source_catalog() -> dict[str, SourceCatalogEntry]:
    """返回 public catalog；hidden/internal 条目不对普通用户展示。"""

    return {name: entry for name, entry in source_catalog().items() if entry.visibility == "public"}


def sources_by_category(category: str) -> list[SourceCatalogEntry]:
    """按正式 catalog category 查询所有条目。"""

    if category not in SOURCE_CATEGORIES:
        return []
    return [entry for entry in source_catalog().values() if entry.category == category]


def default_source_map() -> dict[str, tuple[str, ...]]:
    """返回 ``domain:capability`` 到默认源名的声明式映射。"""

    result: dict[str, list[str]] = {}
    for entry in source_catalog().values():
        for key in entry.default_for:
            result.setdefault(key, []).append(entry.name)
    return {key: tuple(names) for key, names in sorted(result.items())}


def available_source_catalog(config: Any) -> dict[str, SourceCatalogEntry]:
    """按运行时配置过滤 public catalog。

    过滤口径与当前 ``/api/v1/sources`` 保持一致：源未禁用，且 required /
    self_hosted 凭据已满足。
    """

    from souwen.registry.meta import has_required_credentials

    result: dict[str, SourceCatalogEntry] = {}
    for name, entry in public_source_catalog().items():
        if not config.is_source_enabled(name):
            continue
        if not has_required_credentials(config, name, entry):
            continue
        result[name] = entry
    return result


__all__ = [
    "SourceCategory",
    "SourceCatalogEntry",
    "source_categories",
    "source_catalog",
    "public_source_catalog",
    "sources_by_category",
    "default_source_map",
    "available_source_catalog",
]
