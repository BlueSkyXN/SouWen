"""SouWen 数据源注册表（v0 兼容 shim）

v1 已经把单一事实源迁到 `souwen.registry`（含执行适配：MethodSpec）。
本模块保留全部 v0 公开符号，内部从 `souwen.registry.views` 派生。

v0 公开 API（全部保留）：
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

迁移备注（v1 → v0 category 映射）：
    v1 的 10 个 domain 中有 8 个与 v0 重名：paper / patent / social / video / knowledge /
    developer / cn_tech / office。另外：
      - v1 `web` 下的 scraper / self_hosted + 部分 SERP API → v0 `general`
      - v1 `web` 下的 AI/语义 API → v0 `professional`
      - v1 `knowledge` → v0 `wiki`
      - v1 `archive` → v0 `fetch`（Wayback 原本就在 fetch 列表）
    映射规则实现在 `souwen.registry.views._v0_category_for`。
"""

from __future__ import annotations

from dataclasses import dataclass

from souwen.registry import views as _views
from souwen.registry.adapter import INTEGRATIONS

# v0 公开常量 —— 保持原符号
INTEGRATION_TYPES: frozenset[str] = INTEGRATIONS

INTEGRATION_TYPE_LABELS: dict[str, str] = {
    "open_api": "公开接口 — 免配置 / 官方开放 API",
    "scraper": "爬虫抓取 — 无官方 API / 需 TLS 伪装",
    "official_api": "授权接口 — 需 API Key",
    "self_hosted": "自托管 — 需自建服务实例",
}


@dataclass(frozen=True, slots=True)
class SourceMeta:
    """数据源元数据（v0 兼容视图）

    这是 v1 `SourceAdapter` 的**只读投影**。仅保留 v0 原有字段：
        name / category / integration_type / config_field / description

    v0 的 category 值：
        paper | patent | general | professional | social | office |
        cn_tech | developer | wiki | video | fetch
    （对应 v1 的 domain，通过 `_v0_category_for()` 映射）

    新代码应使用 `from souwen.registry import get, by_domain` 等 v1 API。
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
    """从注册表派生 v0 SourceMeta 视图。

    注意：一个 adapter 只产生一个 SourceMeta（使用 v0 category 映射）。
    跨域（如 Tavily domain=web + extra_domains={fetch}）在 v0 视图里只显示
    主 category。这是 v0 的行为（source_registry 里也只登记一个类别）。
    """
    result: dict[str, SourceMeta] = {}
    for adapter in _views.all_adapters().values():
        # v0 ALL_SOURCES 被排除的源（experimental/待修复）也要保留到 source_registry 视图
        # ——v0 source_registry 本身就登记了它们。
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


# ── v0 公开 API（签名不变）──────────────────────────────────

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
        category: v0 分类标签（paper / patent / general / professional / social /
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
    return [
        meta
        for meta in _meta_view().values()
        if meta.integration_type == integration_type
    ]


# frozenset of all names —— 即时从 registry 派生
# 与 v0 相比：
#   - v0 里 `twitter` / `facebook` 登记在 social
#   - v1 保留这些 + 新增 `bing_cn` / `ddg_news` / `ddg_images` / `ddg_videos` / `metaso` 等
# 因此这个集合**允许比 v0 大一些**——新增源是正常演进。
def _compute_all_source_names() -> frozenset[str]:
    return frozenset(_meta_view().keys())


# 保留 v0 的名字（立即计算；消费者一般只做 `name in ALL_SOURCE_NAMES`）
ALL_SOURCE_NAMES: frozenset[str] = _compute_all_source_names()
