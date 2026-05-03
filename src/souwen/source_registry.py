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

    字段语义注解：
        - ``credential_fields`` / ``risk_level`` / ``risk_reasons`` /
          ``distribution`` / ``package_extra`` / ``stability`` 均存储
          ``SourceAdapter`` 上的 ``resolved_*`` 投影（即已根据兼容字段如
          ``high_risk`` tag、``v0_all_sources:exclude`` tag、scraper 默认 extra
          推断出的最终值），消费者无需再访问 adapter 本体。
        - ``distribution`` 在外部插件场景会被 ``_build_source_meta_view`` 强制改写
          为 ``"plugin"``，与 adapter 上的声明可能不同。
        - ``key_requirement`` 是 ``auth_requirement`` 的别名 property，保持
          doctor / API / Panel 的历史字段名兼容。

    新代码可直接使用 `from souwen.registry import get, by_domain` 等 API。
    """

    name: str
    category: str
    integration_type: str
    config_field: str | None
    description: str
    needs_config: bool
    auth_requirement: str
    #: 等同于 ``adapter.resolved_credential_fields``：显式 ``credential_fields``
    #: 优先；为空时回退为 ``(config_field,)``；都为空则 ``()``。
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
        return cfg.resolve_base_url(source_name) or cfg.resolve_api_key(source_name, field)
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
    """判断当前配置是否满足该源的"运行时凭据要求"。

    回答的问题是："这个源现在能不能跑？"——也就是 doctor / `/api/v1/sources` /
    admin source config 中"是否对外可见 / 是否能投入调度"的判定口径。

    返回 ``True`` 的情况：
        - ``auth_requirement`` ∈ {``none``, ``optional``}：缺凭据也照样可用；
        - 源未声明任何 ``credential_fields``（如 fetch 类的 builtin scraper）；
        - ``required`` / ``self_hosted`` 源所有字段都已配置。

    与 :func:`has_configured_credentials` 的区别：
        - **本函数**回答"运行时是否满足"——免配置/可选凭据源永远是 ``True``，因为
          它们就算没 Key 也合法可用。
        - **has_configured_credentials** 回答"用户是否显式配置了 Key"——免凭据源
          永远是 ``False``，因为它们根本没有 Key 可配。
        admin source config 同时返回这两个布尔值（``credentials_satisfied`` /
        ``has_api_key``），区分"该源可用"与"用户给了 Key"。
    """
    if meta.auth_requirement in {"none", "optional"}:
        return True
    if not meta.credential_fields:
        return True
    return not missing_credential_fields(cfg, source_name, meta)


def has_configured_credentials(cfg: Any, source_name: str, meta: Any) -> bool:
    """判断该源声明的凭据字段是否已全部配置。

    回答的问题是："用户给了 Key 吗？"——用于 admin source config 的
    ``has_api_key`` 字段，以及 CLI ``souwen config source`` 详情页的
    "API Key: ✅ 已配置 / ⬜ 未配置" 提示。

    返回 ``False`` 的情况：
        - 源未声明任何 ``credential_fields``：免配置源根本没 Key 可配置，所以从
          "是否配置了 Key"的视角看，永远是 ``False``。这与
          :func:`has_required_credentials` 在同样输入下返回 ``True`` 是有意的
          反向设计：见该函数 docstring 的对照说明。
        - 声明了字段但至少一个未配置。

    返回 ``True`` 仅当：声明的所有 ``credential_fields`` 都解析到非空值。
    """
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
