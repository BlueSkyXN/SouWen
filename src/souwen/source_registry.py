"""SouWen 数据源元数据视图

`souwen.registry` 是单一事实源（含执行适配 MethodSpec）。本模块对外提供基于
分类（category）的便捷视图与查询函数，从 `souwen.registry.views` 派生。

公开 API：
    SourceMeta              —— 数据类（只读字段，视图）
    INTEGRATION_TYPES       —— 4 种集成类型常量集
    INTEGRATION_TYPE_LABELS —— 用户可读标签
    get_all_sources()       —— dict[name, SourceMeta]
    get_source(name)        —— SourceMeta | None
    is_known_source(name)   —— bool
    get_scraper_sources()   —— list[str]
    get_sources_by_category(category)        —— list[SourceMeta]
    get_sources_by_integration_type(itype)   —— list[SourceMeta]
    get_sources_by_auth_requirement(requirement) —— list[SourceMeta]
    get_sources_by_distribution(distribution)     —— list[SourceMeta]
    ALL_SOURCE_NAMES        —— frozenset[str]

domain → category 映射：
    10 个 domain 中有 8 个直接对应 category：paper / patent / social / video /
    knowledge / developer / cn_tech / office。另外：
      - `web` 下的 scraper / self_hosted + 部分 SERP API → `general`
      - `web` 下的 AI/语义 API → `professional`
      - `knowledge` → `wiki`
      - `archive` → `fetch`（Wayback 在 fetch 列表）
    映射规则实现在 `souwen.registry.views._v0_category_for`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from souwen.registry import views as _views
from souwen.registry.adapter import AUTH_REQUIREMENTS, DISTRIBUTIONS, INTEGRATIONS

INTEGRATION_TYPES: frozenset[str] = INTEGRATIONS
AUTH_REQUIREMENT_TYPES: frozenset[str] = AUTH_REQUIREMENTS
DISTRIBUTION_TYPES: frozenset[str] = DISTRIBUTIONS

INTEGRATION_TYPE_LABELS: dict[str, str] = {
    "open_api": "公开接口 — 公开开放 API",
    "scraper": "爬虫抓取 — 无官方 API / 需 TLS 伪装",
    "official_api": "官方接口 — 凭据要求见 Auth",
    "self_hosted": "自托管 — 需自建服务实例",
}

AUTH_REQUIREMENT_LABELS: dict[str, str] = {
    "none": "免配置",
    "optional": "可选凭据",
    "required": "必须凭据",
    "self_hosted": "自建实例",
}

OPTIONAL_CREDENTIAL_EFFECT_LABELS: dict[str, str] = {
    "rate_limit": "提升限流",
    "quota": "提升配额",
    "quality": "提升质量",
    "personalization": "个性化/登录态增强",
    "private_access": "访问私有内容",
    "write_access": "写入能力",
    "politeness": "礼貌访问",
    "unknown": "作用待确认",
}

RISK_LEVEL_LABELS: dict[str, str] = {
    "low": "低风险",
    "medium": "中风险",
    "high": "高风险",
}

DISTRIBUTION_LABELS: dict[str, str] = {
    "core": "核心内置",
    "extra": "可选依赖",
    "plugin": "外部插件",
}

STABILITY_LABELS: dict[str, str] = {
    "stable": "稳定",
    "beta": "Beta",
    "experimental": "实验性",
    "deprecated": "已弃用",
}


@dataclass(frozen=True, slots=True)
class SourceMeta:
    """数据源元数据视图

    `SourceAdapter` 的**只读投影**，包含字段：
        name / category / integration_type / config_field / description，以及
        auth/risk/distribution/stability 等 source catalog 元数据。

    category 取值：
        paper | patent | general | professional | social | office |
        cn_tech | developer | wiki | video | fetch
    （由 `_v0_category_for()` 把 adapter 的 domain 映射到对应 category）

    新代码可直接使用 `from souwen.registry import get, by_domain` 等 API。
    """

    name: str
    category: str
    integration_type: str
    config_field: str | None
    description: str
    needs_config: bool
    auth_requirement: str
    credential_fields: tuple[str, ...]
    optional_credential_effect: str | None
    risk_level: str
    risk_reasons: frozenset[str]
    distribution: str
    package_extra: str | None
    stability: str
    default_enabled: bool
    default_for: frozenset[str]

    @property
    def is_scraper(self) -> bool:
        """是否爬虫类源（需要 curl_cffi TLS 指纹支持）"""
        return self.integration_type == "scraper"

    @property
    def key_requirement(self) -> str:
        """兼容 doctor/API 口径的密钥需求字段。"""
        return self.auth_requirement


# ── 派生缓存 ──────────────────────────────────────────────


def _build_source_meta_view() -> dict[str, SourceMeta]:
    """从注册表派生 SourceMeta 视图。

    一个 adapter 只产生一个 SourceMeta（按主 category 映射）。跨域源
    （如 Tavily domain=web + extra_domains={fetch}）只在主 category 下出现。
    """
    result: dict[str, SourceMeta] = {}
    external_names = set(_views.external_plugins())
    for adapter in _views.all_adapters().values():
        # ALL_SOURCES 排除集合外的源（experimental/待修复）也会保留到本视图。
        category = _views._v0_category_for(adapter)
        if category is None:
            continue
        distribution = "plugin" if adapter.name in external_names else adapter.resolved_distribution
        result[adapter.name] = SourceMeta(
            name=adapter.name,
            category=category,
            integration_type=adapter.integration,
            config_field=adapter.config_field,
            description=adapter.description,
            needs_config=adapter.resolved_needs_config,
            auth_requirement=adapter.resolved_auth_requirement,
            credential_fields=adapter.resolved_credential_fields,
            optional_credential_effect=adapter.optional_credential_effect,
            risk_level=adapter.resolved_risk_level,
            risk_reasons=adapter.resolved_risk_reasons,
            distribution=distribution,
            package_extra=adapter.resolved_package_extra,
            stability=adapter.resolved_stability,
            default_enabled=adapter.default_enabled,
            default_for=adapter.default_for,
        )
    return result


# 首次访问时懒构建；后续直接用缓存。内置注册表在启动时填充；
# 外部插件运行时注册/注销时会显式调用 invalidate_source_meta_cache()。
_SOURCE_META_CACHE: dict[str, SourceMeta] | None = None


def _meta_view() -> dict[str, SourceMeta]:
    global _SOURCE_META_CACHE
    if _SOURCE_META_CACHE is None:
        _SOURCE_META_CACHE = _build_source_meta_view()
    return _SOURCE_META_CACHE


def invalidate_source_meta_cache() -> None:
    """清理并重建 SourceMeta 派生缓存。

    外部插件运行时注册/注销 adapter 后，底层 registry 已变化；这里同步刷新
    `get_source()` / `is_known_source()` / `ALL_SOURCE_NAMES` 的视图。
    """
    global _SOURCE_META_CACHE, ALL_SOURCE_NAMES
    _SOURCE_META_CACHE = _build_source_meta_view()
    ALL_SOURCE_NAMES = frozenset(_SOURCE_META_CACHE.keys())


# ── 公开 API ────────────────────────────────────────────────


def get_all_sources() -> dict[str, SourceMeta]:
    """返回所有已注册数据源的字典

    Returns:
        {源名称: SourceMeta} 映射字典
    """
    return dict(_meta_view())


def get_source(name: str) -> SourceMeta | None:
    """按名称获取单个数据源的元数据

    Args:
        name: 数据源名称

    Returns:
        SourceMeta 对象，不存在则返回 None
    """
    return _meta_view().get(name)


def is_known_source(name: str) -> bool:
    """检查是否是已知数据源名称

    Args:
        name: 数据源名称

    Returns:
        True 表示该源已注册，False 表示未知源
    """
    return name in _meta_view()


def get_scraper_sources() -> list[str]:
    """返回所有爬虫类数据源的名称列表

    爬虫类源（integration_type == 'scraper'）使用 BaseScraper，
    需要 curl_cffi TLS 指纹支持。

    Returns:
        爬虫源名称列表
    """
    return [name for name, meta in _meta_view().items() if meta.is_scraper]


def get_sources_by_category(category: str) -> list[SourceMeta]:
    """按内容分类筛选数据源

    Args:
        category: 分类标签（paper / patent / general / professional / social /
            office / cn_tech / developer / wiki / video / fetch）

    Returns:
        该分类下的 SourceMeta 对象列表
    """
    return [meta for meta in _meta_view().values() if meta.category == category]


def get_sources_by_integration_type(integration_type: str) -> list[SourceMeta]:
    """按集成类型筛选数据源

    Args:
        integration_type: 集成类型 — 'open_api' | 'scraper' | 'official_api' | 'self_hosted'

    Returns:
        该集成类型下的 SourceMeta 对象列表
    """
    return [meta for meta in _meta_view().values() if meta.integration_type == integration_type]


def get_sources_by_auth_requirement(requirement: str) -> list[SourceMeta]:
    """按鉴权/配置要求筛选数据源。"""
    return [meta for meta in _meta_view().values() if meta.auth_requirement == requirement]


def get_sources_by_distribution(distribution: str) -> list[SourceMeta]:
    """按推荐分发范围筛选数据源。"""
    return [meta for meta in _meta_view().values() if meta.distribution == distribution]


# ── 凭据解析工具 ──────────────────────────────────────────────


def credential_value(
    cfg: Any,
    source_name: str,
    field: str,
    primary_field: str | None,
    auth_requirement: str | None = None,
) -> str | None:
    """读取单个凭据字段。

    频道级 `sources.<name>.api_key` 只覆盖主 config_field；多字段凭据的
    secondary 字段仍读取 flat config，避免同一个 api_key 被误判成
    client_id 和 secret 同时满足。
    """
    if auth_requirement == "self_hosted" and field == primary_field:
        return cfg.resolve_base_url(source_name) or getattr(cfg, field, None)
    if field == primary_field:
        return cfg.resolve_api_key(source_name, field)
    return getattr(cfg, field, None)


def missing_credential_fields(cfg: Any, source_name: str, meta: Any) -> list[str]:
    """返回尚未满足的凭据字段列表。"""
    fields = tuple(meta.credential_fields)
    if not fields:
        return []
    missing: list[str] = []
    for field in fields:
        value = credential_value(
            cfg,
            source_name,
            field,
            meta.config_field,
            meta.auth_requirement,
        )
        if not value:
            missing.append(field)
    return missing


def has_required_credentials(cfg: Any, source_name: str, meta: Any) -> bool:
    """判断必需凭据是否满足；none/optional 源始终可作为可用候选。"""
    if meta.auth_requirement in {"none", "optional"}:
        return True
    if not meta.credential_fields:
        return True
    return not missing_credential_fields(cfg, source_name, meta)


def has_configured_credentials(cfg: Any, source_name: str, meta: Any) -> bool:
    """判断该源声明的凭据字段是否已全部配置。"""
    if not meta.credential_fields:
        return False
    return not missing_credential_fields(cfg, source_name, meta)


def credential_fields_label(fields: list[str] | tuple[str, ...]) -> str:
    """把多个凭据字段格式化为用户可读标签。"""
    return " / ".join(fields)


# 即时从 registry 派生所有源名称
def _compute_all_source_names() -> frozenset[str]:
    return frozenset(_meta_view().keys())


# 立即计算（消费者一般只做 `name in ALL_SOURCE_NAMES`）
ALL_SOURCE_NAMES: frozenset[str] = _compute_all_source_names()
