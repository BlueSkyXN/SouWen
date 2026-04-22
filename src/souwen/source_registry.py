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

from souwen.registry import views as _views
from souwen.registry.adapter import INTEGRATIONS

INTEGRATION_TYPES: frozenset[str] = INTEGRATIONS

INTEGRATION_TYPE_LABELS: dict[str, str] = {
    "open_api": "公开接口 — 免配置 / 官方开放 API",
    "scraper": "爬虫抓取 — 无官方 API / 需 TLS 伪装",
    "official_api": "授权接口 — 需 API Key",
    "self_hosted": "自托管 — 需自建服务实例",
}


@dataclass(frozen=True, slots=True)
class SourceMeta:
    """数据源元数据视图

    `SourceAdapter` 的**只读投影**，包含字段：
        name / category / integration_type / config_field / description

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

    @property
    def is_scraper(self) -> bool:
        """是否爬虫类源（需要 curl_cffi TLS 指纹支持）"""
        return self.integration_type == "scraper"


# ── 派生缓存 ──────────────────────────────────────────────


def _build_source_meta_view() -> dict[str, SourceMeta]:
    """从注册表派生 SourceMeta 视图。

    一个 adapter 只产生一个 SourceMeta（按主 category 映射）。跨域源
    （如 Tavily domain=web + extra_domains={fetch}）只在主 category 下出现。
    """
    result: dict[str, SourceMeta] = {}
    for adapter in _views.all_adapters().values():
        # ALL_SOURCES 排除集合外的源（experimental/待修复）也会保留到本视图。
        category = _views._v0_category_for(adapter)
        if category is None:
            continue
        result[adapter.name] = SourceMeta(
            name=adapter.name,
            category=category,
            integration_type=adapter.integration,
            config_field=adapter.config_field,
            description=adapter.description,
        )
    return result


# 首次访问时懒构建；后续直接用缓存（注册表是启动时一次性填充的，运行期不可变）
_SOURCE_META_CACHE: dict[str, SourceMeta] | None = None


def _meta_view() -> dict[str, SourceMeta]:
    global _SOURCE_META_CACHE
    if _SOURCE_META_CACHE is None:
        _SOURCE_META_CACHE = _build_source_meta_view()
    return _SOURCE_META_CACHE


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


# 即时从 registry 派生所有源名称
def _compute_all_source_names() -> frozenset[str]:
    return frozenset(_meta_view().keys())


# 立即计算（消费者一般只做 `name in ALL_SOURCE_NAMES`）
ALL_SOURCE_NAMES: frozenset[str] = _compute_all_source_names()
